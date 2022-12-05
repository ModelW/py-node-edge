from pytest import raises

from node_edge import *
from node_edge.exceptions import *


def test_wrong_dep():
    ne = NodeEngine(
        dict(dependencies=dict(xxx_xxx_xxx_xxx_xxx="^1.2.0")), keep_lock=False
    )

    with raises(NodeEdgeException):
        ne.create_env()


def test_fail_env_dir():
    ne = NodeEngine({}, env_dir_candidates=["/foo/bar"])

    with raises(NodeEdgeException):
        ne.create_env()
