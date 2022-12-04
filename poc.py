from node_edge import NodeEngine

ne = NodeEngine(
    {
        "dependencies": {
            "axios": "^1.2.0",
        },
    },
    debug=True,
)

with ne:
    axios = ne.import_from("axios")
    print(axios)
    # print(axios.get('https://httpbin.org/robots.txt').data)
