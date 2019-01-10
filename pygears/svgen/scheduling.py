import typing as pytypes
from dataclasses import dataclass

import hdl_types as ht

from .hdl_preprocess import InstanceVisitor

async_types = [ht.Yield]


def check_if_blocking(stmt):
    if type(stmt) in async_types:
        return stmt
    elif isinstance(stmt, ht.Block):
        return stmt
    else:
        return None


def find_hier_blocks(body):
    hier = []
    for stmt in body:
        b = check_if_blocking(stmt)
        if b:
            hier.append(b)
    return hier


@dataclass
class CBlock:
    parent: pytypes.Any
    child: list
    hdl_block: pytypes.Any


@dataclass
class MutexCBlock(CBlock):
    parent: pytypes.Any
    child: list
    hdl_block: pytypes.Any


@dataclass
class SeqCBlock(CBlock):
    parent: pytypes.Any
    child: list
    hdl_block: pytypes.Any


@dataclass
class Leaf:
    parent: pytypes.Any
    hdl_block: pytypes.Any
    state_id: pytypes.Any


class Scheduler(InstanceVisitor):
    def __init__(self):
        self.scope = []

    def enter_block(self, block):
        self.scope.append(block)

    def exit_block(self):
        self.scope.pop()

    def visit_block(self, cnode, body):
        self.enter_block(cnode)

        for stmt in body:
            if isinstance(stmt, (ht.Block, ht.Yield)):
                cnode.child.append(self.visit(stmt))

        self.exit_block()

        return cnode

    def visit_Module(self, node):
        cblock = SeqCBlock(parent=None, hdl_block=node, child=[])
        return self.visit_block(cblock, node.stmts)

    def visit_IntfBlock(self, node):
        cblock = SeqCBlock(parent=self.scope[-1], hdl_block=node, child=[])
        return self.visit_block(cblock, node.stmts)

    def visit_Yield(self, node):
        return Leaf(parent=self.scope[-1], hdl_block=node)
