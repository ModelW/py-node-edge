# Getting started

Node Edge is a tool that lets you call Node functions from Python. It will
automatically install dependencies from NPM and let you use them directly.
Javascript objects and modules are proxied as best as possible into Python
idioms and syntax so that you can use them almost as if they were native Python.

## Installation

Node Edge is available on PyPI and can be installed with pip:

```bash
pip install node_edge
```

## Usage

In order to call JavaScript functions from Python, you need to create an
instance of the NodeEngine class. This class will automatically install
dependencies from NPM and make them available to you.

```python
from node_edge import NodeEngine

with NodeEngine({}) as engine:
    ...  # Use the engine here
```

The options of the constructor are the literal content of the package.json file
that will be inserted in the "environment" directory. This is a directory
entirely managed by NodeEdge and it will basically contain the node_modules +
this package file you're defining.

So let's say you want to use Axios from Python. You can go like this:

```python
from node_edge import NodeEngine

package = {
    "dependencies": {
        "axios": "^1.2.0",
    },
}


with NodeEngine(package) as ne:
    axios = ne.import_from("axios")
    print(axios.get("https://httpbin.org/robots.txt").data)
```

```{note}
In most cases, Promises will be automatically awaited. This
will block the thread you're in, that's a design choice made for convenience
and simplicity.
```

```{note}
As a general rule, the performance of Node Edge is shit. That's
not the goal of this lib. See the [Performance](performance.md) section for
more details on this insanity
```
