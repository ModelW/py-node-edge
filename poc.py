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
    print(ne.eval("2 + 2"))
