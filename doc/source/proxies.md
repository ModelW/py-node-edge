# Proxies

When you're making a call to Node Edge, one of two things can happen:

-   Either the return value can be serialized into JSON, in which case you get a
    copy of the Node value that has been serialized through JSON (this it's not
    "connected" to Node anymore)
-   Or the return value cannot be serialized into JSON, in which case you get a
    proxy object that will let you call Node functions from Python.

As you might know, the typing of objects in JS is a bit ambiguous and does not
always map super well to Pythonic concepts. That's why we've got three different
proxies:

-   `JavaScriptProxy` &mdash; Is a proxy for a "class instance" or a "module" or
    anything that will generally have methods you can call and stuff like this.
-   `JavaScriptArrayProxy` &mdash; Arrays are a special type of objects in JS
    and they _can_ be detected so if we encounter one that's the proxy you'll be
    getting
-   `JavaScriptMappingProxy` &mdash; This one will treat the object as a mapping
    (dict-like) and will let you access items on it.

## JavaScriptProxy

This is the most common proxy you'll be getting. Basically most of the calls
that you make that don't end up in JSON will be this.

```python
from node_edge import NodeEngine

with NodeEngine({}) as ne:
    axios = ne.import_from("axios")
```

What you got here is a `JavaScriptProxy`. You can either do `axios.get` or
`axios["get"]`, both will be resolved to a pointer to the `get` method.

However, it's not a true mapping. Typically if it did implement the `Mapping`
interface, the `get()` method would get an item from the dictionary instead of
calling the `get` method on the object.

Other than that you can do all the regular attribute operations:

```python
axios.foo = 42
del axios.foo
```

This will impact the "remote" object directly.

## JavaScriptArrayProxy

If the returned value is an array, we detect it and return a
`JavaScriptArrayProxy` which implements the `MutableSequence` interface.

```python
from node_edge import NodeEngine

with NodeEngine({}) as ne:
    arr = ne.eval("['foo', () => 42]")
    print(len(arr))  # 2

    arr.append("bar")
    print(len(arr))  # 3

    del arr[1]
    print(len(arr))  # 2
```

> _Note_ &mdash; Here we put a function in the array in order to make it
> non-JSON-serializable and thus trigger the return of a proxy.

## JavaScriptMappingProxy

Most of the time if you've got a proxy, it's because the object is not
JSON-serializable. However, if it's a mapping, we can still return a proxy that
will implement the `MutableMapping` interface.

This is done by transforming the a `JavaScriptProxy` into a
`JavaScriptMappingProxy` using the `as_mapping()` method.

```python
from node_edge import NodeEngine, as_mapping

with NodeEngine({}) as ne:
    axios = ne.import_from("axios")
    resp = axios.get("https://httpbin.org/robots.txt")
    headers = as_mapping(resp.headers)
    print({**headers})
```

In the cas above, the headers from Axios are stored in a special class that
won't be serialized into JSON but can be converted into a mapping. The
`print({**headers})` statement serves as a demonstration that this mapping can
then be converted into a regular dictionary and printed.

## Calls

Something that you've seen so far but have not been explained is how function
calls work.

Basically, the `JavaScriptProxy` implements the `__call__` method (with only
`*args`, not `**kwargs`). When you call it, it will forward the call to the JS
side, wait for the promise to resolve if required and then return the result.

The arguments you pass can either be:

-   Something that can be serialized into JSON
-   Any of the proxies

The proxy can be nested deep inside the JSON structure, it will be detected and
converted back into its JS counterpart once in Node.

For example, you can imagine something like this:

```python
from node_edge import NodeEngine

with NodeEngine({}) as ne:
    ne.eval(
        """
        function foo() {
            return 'foo';
        }

        function bar() {
            return 'bar';
        }

        function execFromMap(functions, name) {
            return functions[name]();
        }
        """
    )

    foo = ne.eval("foo")
    bar = ne.eval("bar")
    exec_from_map = ne.eval("execFromMap")

    print(exec_from_map({"foo": foo, "bar": bar}, "foo"))  # foo
```

For now you cannot give Python callbacks as arguments, as it's not coded yet and
coding it would probably be a bit confusing thread-wise. My advice is to create
a Node function (using `eval()` like above) that will deal with all the JS-side
logic and return a Promise that will resolve with the output you're expecting.
Since function calls automatically await the output, you'll simply get your
output like that.

If you want a long-lived part of your code to be executed in Node and
communicating with Python, that's clearly out of scope for now.
