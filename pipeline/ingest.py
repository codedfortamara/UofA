"""Ingestion stage -- the local stand-in for API Gateway + a validation Lambda.

Runs a tiny HTTP server that accepts ``POST /events`` with a JSON body, validates
it, and (if valid) puts it on the stream. Invalid payloads get a ``400`` with the
full list of problems. This is the pipeline's front door.

We use only the standard library's ``http.server`` so the whole project runs with
zero third-party dependencies -- fewer moving parts is easier to deploy, and easy
deployment is the forward deployed engineer's whole game.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .stream import Stream
from .validate import validate_event


def make_handler(stream):
    """Build a request handler bound to a specific stream.

    Returning a class from a function (a closure) is how we inject the stream
    dependency, which keeps the handler testable: a test can pass a throwaway
    stream backed by a temp file instead of touching real infrastructure.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/events":
                return self._send(404, {"error": "not found"})

            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON"})

            errors = validate_event(event)
            if errors:
                return self._send(
                    400, {"error": "validation failed", "details": errors}
                )

            offset = stream.put(event)
            return self._send(202, {"status": "accepted", "offset": offset})

        def log_message(self, *args):
            pass  # silence per-request logging to keep test/CI output clean

        def _send(self, code, body):
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def serve(host="127.0.0.1", port=8000, stream=None):
    stream = stream or Stream()
    server = ThreadingHTTPServer((host, port), make_handler(stream))
    print(f"ingestion API listening on http://{host}:{port}  (POST /events)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
