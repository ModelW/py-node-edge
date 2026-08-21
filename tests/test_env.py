import pytest

from node_edge import NodeEngine
from node_edge.exceptions import (
    NodeEdgeException,
)


def test_wrong_dep():
    ne = NodeEngine(dict(dependencies=dict(xxx_xxx_xxx_xxx_xxx="^1.2.0")))

    with pytest.raises(NodeEdgeException):
        ne.create_env()


def test_fail_env_dir():
    ne = NodeEngine({}, env_dir_candidates=["/foo/bar"])

    with pytest.raises(NodeEdgeException):
        ne.create_env()
