from node_edge import NodeEngine


def test_resolve_awaits_promises():
    with NodeEngine({}) as ne:
        promise = ne.eval("Promise.resolve(42)")
        assert ne.resolve(promise) == 42


def test_resolve_passes_through_plain_values():
    with NodeEngine({}) as ne:
        assert ne.resolve(42) == 42
        assert ne.resolve("foo") == "foo"
        assert ne.resolve(None) is None


def test_resolve_passes_through_non_awaitable_pointers():
    with NodeEngine({}) as ne:
        obj = ne.eval("({foo: () => 'bar'})")
        assert ne.resolve(obj) is obj
