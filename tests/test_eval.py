from pytest import raises

from node_edge import NodeEngine
from node_edge.exceptions import *


def test_eval():
    with NodeEngine({}) as ne:
        assert ne.eval("1 + 1") == 2
        assert ne.eval("[1, 2, 3, 4, {foo: 42}]") == [1, 2, 3, 4, {"foo": 42}]

        with raises(JavaScriptError):
            ne.eval("throw new Error('fail')")
