import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qsl, urlparse

import pytest

from node_edge import NodeEngine
from node_edge.exceptions import JavaScriptError


@pytest.fixture
def http_server():
    """A tiny local HTTP server echoing query-string arguments as JSON."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            args = dict(parse_qsl(urlparse(self.path).query))
            body = json.dumps({"args": args}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", f"{len(body)}")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}"

    server.shutdown()


def test_import(http_server):
    with NodeEngine(dict(dependencies=dict(axios="^1.2.0"))) as ne:
        axios = ne.import_from("axios")
        resp = axios.get(f"{http_server}/get?foo=42")
        assert resp.data["args"]["foo"] == "42"

        with pytest.raises(JavaScriptError):
            ne.import_from("xxx-xxx-xxx-xxx-xxx")
