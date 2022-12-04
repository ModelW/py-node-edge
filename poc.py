from node_edge import NodeEngine

package = {
    "dependencies": {
        "axios": "^1.2.0",
    },
}


with NodeEngine(package, debug=True) as ne:
    axios = ne.import_from("axios")
    print(axios.get("https://httpbin.org/robots.txt").data)
