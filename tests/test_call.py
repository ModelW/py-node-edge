import re

from _pytest.python_api import raises

from node_edge import JavaScriptError, NodeEdgeTypeError, NodeEngine


def test_call():
    with NodeEngine({}) as ne:
        ne.eval(
            """
            function doSomething(cbList) {
                let out = 0;

                for (cb of cbList) {
                    if (typeof cb === "function") {
                        out += cb();
                    } else {
                        out += cb;
                    }
                }

                return out;
            }

            function doSomethingElse(cbMap) {
                let out = 0;

                for (const [key, cb] of Object.entries(cbMap)) {
                    if (typeof cb === "function") {
                        out += cb();
                    } else {
                        out += cb;
                    }
                }

                return out;
            }

            function return42() {
                return 42;
            }

            function fail() {
                throw new Error("fail");
            }
            """
        )

        do_something = ne.eval("doSomething")
        do_something_else = ne.eval("doSomethingElse")
        return42 = ne.eval("return42")
        fail = ne.eval("fail")

        assert do_something([1, 2, 3, 4, 5]) == 15
        assert do_something([1, 2, 3, 4, return42]) == 52
        assert (
            do_something_else(
                {
                    "foo": 1,
                    "bar": 2,
                    "baz": 3,
                    "qux": 4,
                }
            )
            == 10
        )
        assert (
            do_something_else(
                {
                    "foo": 1,
                    "bar": 2,
                    "baz": 3,
                    "qux": return42.__dict__["__pointer__"],
                }
            )
            == 48
        )

        with raises(NodeEdgeTypeError):
            do_something(object())

        with raises(
            JavaScriptError,
            match=re.compile(r"^fail:\nError: fail\n {4}at fail \(evalmachine.*"),
        ):
            fail()
