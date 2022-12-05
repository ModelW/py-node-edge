from pytest import raises

from node_edge import NodeEngine
from node_edge.exceptions import *


def test_import():
    with NodeEngine(dict(dependencies=dict(axios="^1.2.0"))) as ne:
        axios = ne.import_from("axios")
        resp = axios.get("https://httpbin.org/get?foo=42")
        assert resp.data["args"]["foo"] == "42"

        with raises(JavaScriptError):
            ne.import_from("xxx-xxx-xxx-xxx-xxx")
