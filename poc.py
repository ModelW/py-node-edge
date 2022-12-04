from node_edge import NodeEngine, as_mapping

package = {
    "dependencies": {
        "axios": "^1.2.0",
    },
}


with NodeEngine(package, debug=False) as ne:
    axios = ne.import_from("axios")
    resp = axios.get("https://httpbin.org/get")
    print(resp.data)
    print({**as_mapping(resp.headers)})
