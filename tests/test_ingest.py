"""End-to-end test for the ingestion (API Gateway + Lambda) stage.

Spins up the real HTTP server on an ephemeral port and talks to it over the
network, so this exercises the full request -> validate -> stream path.
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from pipeline.ingest import make_handler
from pipeline.stream import Stream


def _post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_api_accepts_valid_and_rejects_invalid(tmp_path):
    stream = Stream(tmp_path / "s.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(stream))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{port}/events"

        code, body = _post(
            url,
            {"event_id": "e1", "user_id": "u1", "event_type": "click",
             "timestamp": "2026-07-25T10:00:00Z"},
        )
        assert code == 202 and body["status"] == "accepted"

        code, body = _post(url, {"event_id": "bad"})
        assert code == 400 and "details" in body
    finally:
        server.shutdown()

    assert stream.size() == 1  # only the valid event made it onto the stream
