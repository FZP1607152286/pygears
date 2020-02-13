from ..pydl import nodes as pydl
from ..pydl.ast import GearContext, FuncContext, Context
from ..pydl.visitor import PydlExprRewriter
from .utils import Scope
from functools import singledispatch
from pygears.typing import Bool, Uint, bitw
from .nodes import AssignValue, CombBlock, HDLBlock, IfElseBlock, FuncReturn, FuncBlock
from .passes import RewriteExitCond, RemoveDeadCode
# from .simplify import simplify

res_true = pydl.ResExpr(Bool(True))
res_false = pydl.ResExpr(Bool(False))


@singledispatch
def in_condition(node, ctx):
    return res_true


def bin_op_reduce(intfs, func, op):
    intf1 = func(intfs[0])

    if len(intfs) == 1:
        return intf1
    else:
        return pydl.BinOpExpr([intf1, bin_op_reduce(intfs[1:], func, op)], op)


@in_condition.register
def _(node: pydl.IntfBlock, ctx):
    return bin_op_reduce(node.intfs, lambda i: pydl.Component(i, 'valid'),
                         pydl.opc.And)


@singledispatch
def opt_in_condition(node, ctx):
    return res_true


@opt_in_condition.register
def _(node: pydl.Loop, ctx):
    return node.test


@opt_in_condition.register
def _(node: pydl.IfBlock, ctx):
    return node.test


def add_to_list(orig_list, extension):
    if extension:
        orig_list.extend(
            extension if isinstance(extension, list) else [extension])


class AliasRewriter(PydlExprRewriter):
    def __init__(self, forwarded):
        self.forwarded = forwarded

    def visit_Name(self, node):
        if ((node.name in self.forwarded) and (node.ctx == 'load')):
            return self.forwarded[node.name]

        return None


def replace_aliases(forwarded, node):
    new_node = AliasRewriter(forwarded).visit(node)
    if new_node is None:
        return node

    return new_node


class HDLGenerator:
    def __init__(self, ctx):
        self.ctx = ctx
        self.block_stack = []
        self.forwarded = Scope()

    @property
    def block(self):
        return self.block_stack[-1]

    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)

        if visitor.__name__ == 'generic_visit' and isinstance(
                node, pydl.Block):
            visitor = getattr(self, 'visit_all_Block', self.generic_visit)

        if visitor.__name__ == 'generic_visit' and isinstance(node, pydl.Expr):
            visitor = getattr(self, 'visit_all_Expr', self.generic_visit)

        if visitor.__name__ == 'generic_visit' and isinstance(
                node, pydl.Statement):
            visitor = getattr(self, 'visit_all_Statement', self.generic_visit)

        return visitor(node)

    def generic_visit(self, node):
        pass

    def generic_traverse(self, node, block):
        for stmt in node.stmts:
            add_to_list(block.stmts, self.visit(stmt))

        return block

    def traverse_block(self, node, block):
        method = 'traverse_' + node.__class__.__name__
        traverse_visitor = getattr(self, method, self.generic_traverse)

        return traverse_visitor(node, block)

    def merge_subscope(self, block):
        subscope = self.forwarded.cur_subscope
        self.forwarded.upscope()

        for name, val in subscope.items.items():
            if block.opt_in_cond != res_true:
                if name in self.forwarded:
                    prev_val = self.forwarded[name]
                else:
                    prev_val = self.ctx.ref(name)

                val = pydl.ConditionalExpr((val, prev_val), block.opt_in_cond)

            self.forwarded[name] = val

    def visit_all_Block(self, node):
        block = HDLBlock(in_cond=self.in_condition(node),
                         opt_in_cond=self.opt_in_condition(node),
                         stmts=[],
                         dflts={})

        if not isinstance(self.block, IfElseBlock):
            self.forwarded.subscope()

        res = self.traverse_block(node, block)

        if isinstance(self.block, IfElseBlock):
            return res

        self.merge_subscope(block)

        return res

    def visit_Assign(self, node):
        expr = self.visit(node.expr)
        ret = AssignValue(target=node.var, val=expr, dtype=node.var.dtype)

        if (isinstance(node.var, pydl.Name)
                and isinstance(node.var.obj, pydl.Register)):
            if node.var.obj.any_init:
                node.var.obj.val = pydl.CastExpr(expr, node.var.obj.dtype)
                node.var.obj.any_init = False

        if isinstance(node.var, pydl.SubscriptExpr):
            if node.var.val.name not in self.forwarded:
                raise Exception

            var_name = node.var.val.name
            if isinstance(node.var.index, pydl.ResExpr):
                index_val = node.var.index.val
                self.forwarded[var_name][index_val] = expr
            else:
                del self.forwarded[var_name]

        elif isinstance(node.var, pydl.Name):
            self.forwarded[node.var.name] = expr
        else:
            raise Exception

        # print('------------')
        # print(node.expr)
        # print(expr)

        return ret

    def visit_all_Expr(self, expr):
        return replace_aliases(self.forwarded, expr)

    def opt_in_condition(self, node):
        return self.visit_all_Expr(opt_in_condition(node, self.ctx))

    def in_condition(self, node):
        return self.visit_all_Expr(in_condition(node, self.ctx))

    def visit_AssignValue(self, node):
        return node

    def visit_ContainerBlock(self, node):
        block = IfElseBlock(stmts=[], dflts={})
        self.block_stack.append(block)
        subscopes = []
        forwards = set()

        for stmt in node.stmts:
            self.forwarded.subscope()

            add_to_list(block.stmts, self.visit(stmt))
            subs = self.forwarded.cur_subscope
            subs.opt_in_cond = block.stmts[-1].opt_in_cond
            subscopes.append(subs)
            forwards.update(subs.items.keys())

            self.forwarded.upscope()

        for name in forwards:
            if name in self.forwarded:
                val = self.forwarded[name]
            else:
                val = self.ctx.ref(name)

            for subs in reversed(subscopes):
                if name in subs.items:
                    val = pydl.ConditionalExpr((subs.items[name], val),
                                               cond=subs.opt_in_cond)

            self.forwarded[name] = val

        self.block_stack.pop()
        return block


class ModuleGenerator(HDLGenerator):
    def __init__(self, ctx, state_id):
        super().__init__(ctx)
        self.state_id = state_id
        self.cur_state_id = 0

    @property
    def cur_state(self):
        return self.cur_state_id == self.state_id

    def generic_traverse(self, node, block):
        if self.state_id not in node.state:
            return block

        self.block_stack.append(block)
        self.cur_state_id = list(node.state)[0]

        for stmt in node.stmts:
            if self.state_id in stmt.state:
                if self.cur_state_id not in stmt.state:
                    self.cur_state_id = list(stmt.state)[0]

                add_to_list(block.stmts, self.visit(stmt))
            elif self.cur_state:
                block.stmts.append(
                    AssignValue(self.ctx.ref('state', ctx='store'),
                                list(stmt.state)[0],
                                exit_cond=res_false))
                break

        if self.cur_state_id not in node.state:
            self.cur_state_id = list(node.state)[0]

        self.block_stack.pop()
        return block

    def visit_Module(self, node):
        block = HDLBlock(stmts=[], dflts={})
        self.ctx.scope['rst_cond'] = pydl.Variable('rst_cond', Bool)
        self.ctx.scope['cycle_done'] = pydl.Variable('cycle_done', Bool)

        block.stmts.append(
            AssignValue(self.ctx.ref('cycle_done', 'store'), res_true))
        block.stmts.append(
            AssignValue(self.ctx.ref('rst_cond', 'store'), res_false))

        block = self.traverse_block(node, block)
        block.stmts.append(
            AssignValue(self.ctx.ref('rst_cond', 'store'), res_true))
        return block

    def opt_in_condition(self, node):
        if not self.cur_state:
            return res_true

        return self.visit_all_Expr(opt_in_condition(node, self.ctx))

    def in_condition(self, node):
        if not self.cur_state:
            return res_true

        return self.visit_all_Expr(in_condition(node, self.ctx))

    def visit_IntfBlock(self, node):
        if self.state_id not in node.state:
            return []

        block = self.visit_all_Block(node)

        for i in node.intfs:
            block.stmts.append(
                AssignValue(target=self.ctx.ref(i.name, 'ready'),
                            val=res_true))

        return block

    def visit_Loop(self, node):
        if self.state_id not in node.state:
            return []

        block = HDLBlock(in_cond=self.in_condition(node),
                         opt_in_cond=self.opt_in_condition(node),
                         stmts=[],
                         dflts={})

        looped_init = False
        for name in self.forwarded:
            if isinstance(self.ctx.scope[name], pydl.Register):
                if not looped_init:
                    looped_init = True
                    self.ctx.scope['looped'] = pydl.Register('looped',
                                                             val=res_false)

                self.forwarded[name] = pydl.ConditionalExpr(
                    (self.ctx.ref(name), self.forwarded[name]),
                    self.ctx.ref('looped'))

        self.forwarded.subscope()

        block = self.traverse_block(node, block)

        block.exit_cond = pydl.UnaryOpExpr(self.opt_in_condition(node),
                                           pydl.opc.Not)

        self.merge_subscope(block)
        # self.forwarded.upscope()

        if looped_init:
            block.stmts.append(
                AssignValue(target=self.ctx.ref('looped'), val=res_true))

        if 'state' in self.ctx.scope:
            block.stmts.insert(
                0,
                AssignValue(target=self.ctx.ref('cycle_done'),
                            val=self.ctx.ref('state', ctx='en')))
        else:
            block.stmts.insert(
                0, AssignValue(target=self.ctx.ref('cycle_done'),
                               val=res_false))

        block.stmts.append(
            AssignValue(target=self.ctx.ref('cycle_done'), val=res_true))

        if 'state' in self.ctx.scope:
            if (self.cur_state and self.state_id != list(node.state)[0]
                    and node.blocking):
                block.stmts.append(
                    AssignValue(self.ctx.ref('state', ctx='store'),
                                list(node.state)[0],
                                exit_cond=res_false))

        return block

    def visit_IntfLoop(self, node):
        if self.state_id not in node.state:
            return []

        block = self.visit_Loop(node)

        block.exit_cond = pydl.ArrayOpExpr(
            pydl.SubscriptExpr(pydl.Component(node.intf, 'data'),
                               pydl.ResExpr(-1)), pydl.opc.BitAnd)

        block.stmts.append(
            AssignValue(target=self.ctx.ref(node.intf.name, 'ready'),
                        val=res_true))

        # block = self.traverse_block(node, block)
        return block

    def visit_Yield(self, node):
        if not self.cur_state:
            return []

        block = HDLBlock(exit_cond=pydl.Component(node.ports[0], 'ready'),
                         stmts=[],
                         dflts={})

        exprs = node.expr.val

        assert len(exprs) == len(self.ctx.out_ports)

        for expr, port in zip(exprs, self.ctx.out_ports):
            if isinstance(expr, pydl.ResExpr) and expr.val is None:
                continue

            block.stmts.append(
                AssignValue(self.ctx.ref(port.name, ctx='store'),
                            self.visit_all_Expr(expr)))

        return block


class FunctionGenerator(HDLGenerator):
    def visit_Function(self, node, **kwds):
        block = FuncBlock(stmts=[],
                          dflts={},
                          args=node.args,
                          name=node.name,
                          ret_dtype=self.ctx.ret_dtype)

        self.func_block = block

        return self.traverse_block(node, block)

    def visit_Return(self, node):
        return FuncReturn(func=self.func_block, expr=self.visit(node.expr))


def generate(pydl_ast, ctx: GearContext):
    state_num = len(pydl_ast.state)

    if state_num > 1:
        ctx.scope['state'] = pydl.Register(
            'state', pydl.ResExpr(Uint[bitw(state_num - 1)](0)))

    stateblock = IfElseBlock(stmts=[], dflts={})
    for i in range(state_num):
        v = ModuleGenerator(ctx, i)
        res = v.visit(pydl_ast)
        stateblock.stmts.append(res)

        if state_num > 1:
            res.opt_in_cond = pydl.BinOpExpr(
                (ctx.ref('state'), pydl.ResExpr(i)), pydl.opc.Eq)

    modblock = CombBlock(stmts=[stateblock], dflts={})

    # print(modblock)
    RewriteExitCond(ctx).visit(modblock)
    # print(modblock)
    RemoveDeadCode(ctx).visit(modblock)
    # print(modblock)
    gen_all_funcs(modblock, ctx)

    return modblock


def generate_func(pydl_ast, ctx: FuncContext):
    v = FunctionGenerator(ctx)
    res = v.visit(pydl_ast)

    # print(res)
    gen_all_funcs(res, ctx)

    return res


def gen_all_funcs(block, ctx: Context):
    for f_ast, f_ctx in ctx.functions.values():
        block.funcs.append((generate_func(f_ast, f_ctx), f_ctx))
