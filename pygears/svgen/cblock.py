from .inst_visit import InstanceVisitor


def add_to_list(orig_list, extention):
    if extention:
        orig_list.extend(
            extention if isinstance(extention, list) else [extention])


class CBlockVisitor(InstanceVisitor):
    def __init__(self, hdl_preprocess):
        self.hdl = hdl_preprocess
        self.scope = []

    def enter_block(self, block):
        self.scope.append(block)
        if hasattr(block.hdl_block, 'cycle_cond'):
            self.hdl.cycle_cond = block.hdl_block.cycle_cond
        if hasattr(block.hdl_block, 'exit_cond'):
            self.hdl.exit_cond = block.hdl_block.exit_cond
        return self.hdl.visit(block.hdl_block)

    def exit_block(self):
        self.scope.pop()
        self.hdl.cycle_cond = None
        self.hdl.exit_cond = None

    def visit_block(self, node):
        block = self.enter_block(node)

        for c in node.child:
            add_to_list(block.stmts, self.visit(c))

        if block.stmts:
            self.hdl.update_defaults(block)

        self.exit_block()

        return block

    def visit_SeqCBlock(self, node):
        return self.visit_block(node)

    def visit_MutexCBlock(self, node):
        return self.visit_block(node)

    def visit_Leaf(self, node):
        hdl_block = []
        for block in node.hdl_blocks:
            add_to_list(hdl_block, self.hdl.visit(block))
        return hdl_block
