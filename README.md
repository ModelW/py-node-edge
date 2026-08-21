# node-edge

![Unit Tests](https://github.com/ModelW/py-node-edge/actions/workflows/tests.yml/badge.svg)
![Documentation](https://readthedocs.org/projects/node-edge/badge/?version=latest)

This tool allows you to run Node code from Python, including dependency
management:

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

By default, node-edge uses the `node` and `npm` binaries found in your `PATH`.
If you don't have (or don't want) a system-wide Node installation, you can get a
Node runtime bundled as a Python wheel:

```bash
pip install node-edge[node]
```

## Documentation

[✨ **Documentation is there** ✨](https://node-edge.rtfd.io)
