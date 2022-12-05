from pytest import raises

from node_edge import (
    JavaScriptArrayProxy,
    JavaScriptMappingProxy,
    JavaScriptProxy,
    NodeEngine,
    as_mapping,
)
from node_edge.exceptions import *


def test_array_proxy():
    with NodeEngine({}) as ne:
        arr = ne.eval("[() => 42, 'a']")
        assert isinstance(arr, JavaScriptArrayProxy)
        assert repr(arr) == "<JavaScriptArrayProxy [ [Function (anonymous)], 'a' ]>"
        assert arr[0]() == 42
        assert arr[1] == "a"
        assert len(arr) == 2

        arr.append("b")
        assert arr[2] == "b"
        assert len(arr) == 3

        arr[2] = "c"
        assert arr[2] == "c"

        del arr[2]
        assert len(arr) == 2

        with raises(IndexError):
            # noinspection PyStatementEffect
            arr[2]


def test_mapping_proxy():
    with NodeEngine({}) as ne:
        ne.eval("const testRepr = {baz() { return 42; }}")
        test_repr = as_mapping(ne.eval("testRepr"))
        assert repr(test_repr) == "<JavaScriptMappingProxy { baz: [Function: baz] }>"

        ne.eval('const mapping = {foo: 42, bar: "a", baz() { return 42; }}')
        mapping = as_mapping(ne.eval("mapping"))
        assert isinstance(mapping, JavaScriptMappingProxy)
        assert mapping["foo"] == 42
        assert mapping["bar"] == "a"
        assert mapping["baz"]() == 42
        assert len(mapping) == 3
        assert list(mapping.keys()) == ["foo", "bar", "baz"]

        mapping["foo"] = 43
        assert mapping["foo"] == 43

        del mapping["foo"]
        assert len(mapping) == 2

        with raises(KeyError):
            # noinspection PyStatementEffect
            mapping["foo"]


def test_object_proxy():
    with NodeEngine({}) as ne:
        ne.eval("const testRepr = {baz() { return 42; }}")
        test_repr = ne.eval("testRepr")
        assert repr(test_repr) == "<JavaScriptProxy { baz: [Function: baz] }>"

        ne.eval('const obj = {foo: 42, bar: "a", baz() { return 42; }}')
        obj = ne.eval("obj")
        assert isinstance(obj, JavaScriptProxy)
        assert obj.foo == 42
        assert obj["foo"] == 42
        assert obj.bar == "a"
        assert obj.baz() == 42

        obj.foo = 43
        assert obj.foo == 43

        del obj.foo

        with raises(AttributeError):
            # noinspection PyStatementEffect
            obj.foo

        with raises(KeyError):
            # noinspection PyStatementEffect
            obj["foo"]


def test_as_mapping():
    with NodeEngine({}) as ne:
        ne.eval('const obj = {foo: 42, bar: "a", baz() { return 42; }}')
        obj = ne.eval("obj")
        assert isinstance(obj, JavaScriptProxy)
        assert isinstance(as_mapping(obj), JavaScriptMappingProxy)
        assert isinstance(
            as_mapping(obj.__dict__["__pointer__"]), JavaScriptMappingProxy
        )

        with raises(NodeEdgeTypeError):
            as_mapping("foo")  # noqa


def test_get_pointer():
    with NodeEngine({}) as ne:
        promise = ne.eval("new Promise((resolve) => resolve(42))")
        assert ne.await_(promise.__dict__["__pointer__"]) == 42

        with raises(NodeEdgeTypeError):
            ne.await_("foo")  # noqa
