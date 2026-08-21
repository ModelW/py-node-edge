import pytest

from node_edge import NodeEngine
from node_edge.exceptions import NodeEdgeException


def test_dead_engine_raises_instead_of_hanging():
    """
    If the Node process dies, blocked and subsequent calls must raise
    instead of waiting forever (this used to hang CI).
    """
    engine = NodeEngine({})
    engine.start()

    try:
        assert engine.eval("1 + 1") == 2

        engine._remote_proc.kill()
        engine._remote_proc.wait()

        def eval_until_failure():
            # Either the eval fails straight away (engine marked dead) or
            # the pending request is failed by the reader thread.
            for _ in range(10):
                engine.eval("1 + 1")

        with pytest.raises(NodeEdgeException):
            eval_until_failure()
    finally:
        engine.stop()


def test_stop_is_idempotent():
    engine = NodeEngine({})
    engine.start()
    engine.eval("1")
    engine.stop()
    engine.stop()
