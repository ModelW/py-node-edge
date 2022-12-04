from node_edge import NodeEngine

ne = NodeEngine(
    {
        "dependencies": {
            "axios": "^1.2.0",
        },
    },
    debug=False,
)

with ne:
    ptr = ne.eval("new Promise((resolve, reject) => { resolve([1, 2, 3]) })")
    print(ne.await_(ptr))
