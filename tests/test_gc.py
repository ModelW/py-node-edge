import gc
import sys
from time import sleep
from weakref import ref

from pytest import raises

from node_edge import *
from node_edge.exceptions import *


def test_gc():
    with NodeEngine({}) as ne:
        ne.eval(
            """
            class Foo {
                constructor(val) {
                    this.val = val;
                }

                getVal() {
                    return this.val;
                }
            }
            """
        )

        foo = ne.eval("new Foo(() => 42)")
        r1 = ref(foo)
        r2 = ref(foo.__dict__["__pointer__"])
        assert foo.getVal()() == 42

        pointer_id = foo.__dict__["__pointer__"].id

        bar = object()
        assert sys.getrefcount(foo) == sys.getrefcount(bar)

        assert r1() is not None
        assert r2() is not None

        del foo

        sleep(0.1)
        gc.collect()
        sleep(0.1)

        assert r1() is None
        assert r2() is None

        new_foo = JavaScriptProxy(
            JavaScriptPointer(pointer_id, False, False, "fake", ne)
        )

        with raises(JavaScriptError):
            new_foo.getVal()()
