from pytest import raises

from node_edge import NodeEngine
from node_edge.exceptions import *


def test_await():
    with NodeEngine({}) as ne:
        promise = ne.eval("new Promise((resolve) => resolve(42))")
        assert ne.await_(promise) == 42

        promise = ne.eval("new Promise((resolve, reject) => reject(new Error('fail')))")

        with raises(JavaScriptError):
            ne.await_(promise)

        ne.eval("function yolo() {}")
        yolo = ne.eval("yolo")

        with raises(NodeEdgeValueError):
            ne.await_(yolo)
