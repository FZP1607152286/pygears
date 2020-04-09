import inspect
import typing
from . import Context, FuncContext, Function, Submodule, SyntaxError, node_visitor, ir, visit_ast, visit_block, ir_utils
from ..debug import print_func_parse_intro
from pygears import Intf, bind, registry
from pygears.core.partial import combine_arg_kwds, extract_arg_kwds
from pygears.core.port import InPort, HDLConsumer, HDLProducer
from pygears.core.datagear import is_datagear, get_datagear_func
from pygears.core.gear import gear_explicit_params


def form_gear_args(args, kwds, func):
    kwd_args, kwds_only = extract_arg_kwds(kwds, func)
    args_only = combine_arg_kwds(args, kwd_args, func)

    return args_only, kwds_only


class ComplexityExplorer(ir_utils.IrExprVisitor):
    def __init__(self):
        self.operations = 0
        self.names = 0

    def visit_Name(self, node):
        self.names += 1

    def visit_BinOpExpr(self, node):
        self.operations += 1
        super().visit_BinOpExpr(node)

    def visit_ConditionalExpr(self, node):
        self.operations += 1
        super().visit_ConditionalExpr(node)


class Inliner(ir_utils.IrExprRewriter):
    def __init__(self, forwarded):
        self.forwarded = forwarded

    def visit_Name(self, node):
        if ((node.name not in self.forwarded) or (node.ctx != 'load')):
            return None

        val = self.forwarded[node.name]

        if isinstance(val, ir.ResExpr) and getattr(val.val, 'unknown', False):
            return node

        return val


def should_inline(func_ir, func_ctx, args):
    if len(func_ir.stmts) > 1:
        return False

    s = func_ir.stmts[0]

    if not isinstance(s, ir.FuncReturn):
        return False

    v = ComplexityExplorer()
    v.visit(s.expr)

    if v.operations <= 2 and v.names <= len(args):
        return True

    return False


def inline_expr(func_ir, func_ctx, args):
    s = func_ir.stmts[0]
    return Inliner(args).visit(s.expr)


def parse_func_call(func: typing.Callable, args, kwds, ctx: Context):
    ctx_stack = registry('hls/ctx')

    uniqueid = ''
    if isinstance(ctx, FuncContext):
        uniqueid = ctx.funcref.name

    uniqueid += str(len(ctx_stack[0].functions))

    funcref = Function(func, args, kwds, uniqueid=uniqueid)

    if funcref not in ctx_stack[0].functions:
        func_ctx = FuncContext(funcref, args, kwds)
        print_func_parse_intro(func, funcref.ast)
        registry('hls/ctx').append(func_ctx)
        func_ir = visit_ast(funcref.ast, func_ctx)
        registry('hls/ctx').pop()
        ctx_stack[0].functions[funcref] = (func_ir, func_ctx)
    else:
        (func_ir, func_ctx) = ctx_stack[0].functions[funcref]
        funcref_list = list(ctx_stack[0].functions.keys())
        funcref.uniqueid = funcref_list[funcref_list.index(funcref)].uniqueid

    args = func_ctx.argdict(args, kwds)

    if not should_inline(func_ir, func_ctx, args):
        return ir.FunctionCall(operands=list(args.values()),
                               ret_dtype=func_ctx.ret_dtype,
                               name=funcref.name)
    else:
        return inline_expr(func_ir, func_ctx, args)


def call_datagear(func, args, params, ctx: Context):
    f = get_datagear_func(func)
    kwds = gear_explicit_params(f, params)
    kwds = {n: ir.ResExpr(v) for n, v in kwds.items()}
    return parse_func_call(f, args, kwds, ctx)


def call_gear(func, args, kwds, ctx: Context):
    local_in = []
    for i, a in enumerate(args):
        intf = Intf(a.dtype)
        intf.source(HDLProducer())
        local_in.append(intf)

    # local_in = [Intf(a.dtype) for a in args]
    if not all(isinstance(node, ir.ResExpr) for node in kwds.values()):
        raise Exception("Not supproted")

    bind('gear/exec_context', 'compile')
    outputs = func(*local_in, **{k: v.val for k, v in kwds.items()})
    bind('gear/exec_context', 'hls')

    if isinstance(outputs, tuple):
        gear_inst = outputs[0].producer.gear
    else:
        gear_inst = outputs.producer.gear

    in_ports = []
    for a, p in zip(args, gear_inst.in_ports):
        if isinstance(a, ir.Interface):
            in_ports.append(a)
            continue

        intf_name = f'{gear_inst.basename}_{p.basename}'
        p.producer.source(HDLProducer())
        pydl_intf = ir.Variable(intf_name, val=p.producer)
        ctx.scope[intf_name] = pydl_intf
        in_ports.append(pydl_intf)

    out_ports = []
    for p in gear_inst.out_ports:
        intf_name = f'{gear_inst.basename}_{p.basename}'
        pydl_intf = ir.Variable(intf_name, val=p.consumer)
        ctx.scope[intf_name] = pydl_intf
        p.consumer.connect(HDLConsumer())
        out_ports.append(pydl_intf)

    stmts = []
    for a, intf in zip(args, in_ports):
        if a == intf:
            continue

        stmts.append(ir.AssignValue(ir.Name(intf.name, intf, ctx='store'), a))

    ctx.submodules.append(Submodule(gear_inst, in_ports, out_ports))

    if len(out_ports) == 1:
        return ctx.ref(out_ports[0].name), stmts
    else:
        return ir.TupleExpr(tuple(ctx.ref(p.name) for p in out_ports)), stmts
