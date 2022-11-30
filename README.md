# node-edge

This tool allows you to run Node code from Python, including dependency
management:

```python
from node_edge import NodeEngine

package = {
    "dependencies": {
        "axios": "^1.2.0",
    },
    "type": "module",
}

with NodeEngine(package, sync=True) as n:
    with n.context() as ctx:
        axios = ctx.import_from('axios')
        data = axios.get('https://httpbin.org/robots.txt').data
        print(data)
```
