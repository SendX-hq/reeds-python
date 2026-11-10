"""The Reeds API played by Python's built-in HTTP server, for tests/smoke/smoke.py.

    python tests/smoke/server.py 8099

Each request is appended to the log file named by REEDS_SMOKE_LOG (one JSON
object per line), so the smoke test can check what it sent.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

LOG = os.environ.get("REEDS_SMOKE_LOG", "reeds-smoke.log")
BUSY: set[str] = set()


def not_found() -> tuple[int, dict[str, Any], dict[str, str]]:
    error = {"code": "NOT_FOUND", "message": "No such delivery.", "doc_url": "https://developer.getreeds.co/errors/NOT_FOUND"}
    return 404, {"status": "failed", "error": error}, {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass

    def answer(self, method: str) -> None:
        url = urlsplit(self.path)
        body = self.rfile.read(int(self.headers.get("content-length") or 0)).decode()
        with open(LOG, "a", encoding="utf-8") as log:
            entry = {
                "method": method,
                "path": url.path,
                "query": url.query,
                "key": self.headers.get("idempotency-key"),
                "auth": self.headers.get("authorization"),
            }
            log.write(json.dumps(entry) + "\n")
        status, payload, headers = self.route(method, url.path, parse_qs(url.query), body)
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", "req_smoke")
        self.send_header("Content-Length", str(len(data)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):  # the client gave up first (the timeout check)
            self.wfile.write(data)

    def route(self, method: str, path: str, query: dict[str, list[str]], body: str) -> tuple[int, dict[str, Any], dict[str, str]]:
        if path == "/oauth/token":
            return 200, {"access_token": "tok_smoke", "token_type": "Bearer", "expires_in": 3600, "scope": "shipping", "livemode": False}, {}
        if path == "/shipping/v1/coverage":
            return 200, {"status": "success", "data": {"states": [{"state": "Lagos", "pickup": True, "delivery": True}]}}, {}
        if path == "/shipping/v1/wallet":
            time.sleep(2)  # longer than the smoke test's timeout
            return 200, {"status": "success", "data": {"balance": 0, "currency": "NGN", "billing_mode": "prepaid"}}, {}
        if path == "/shipping/v1/deliveries" and method == "POST":
            # The first POST of each run is turned away once: the retry must reuse its key.
            params = json.loads(body)
            if params["reference"] not in BUSY:
                BUSY.add(params["reference"])
                error = {"code": "SERVICE_UNAVAILABLE", "message": "Busy.", "doc_url": "https://developer.getreeds.co/errors/SERVICE_UNAVAILABLE"}
                return 503, {"status": "failed", "error": error}, {"Retry-After": "0"}
            return 201, {"status": "success", "data": {"id": "dlv_1", **params}}, {}
        if path == "/shipping/v1/deliveries":
            after = query.get("starting_after", [None])[0]
            data = [{"id": "dlv_1"}] if after else [{"id": "dlv_3"}, {"id": "dlv_2"}]
            return 200, {"status": "success", "data": data, "has_more": not after}, {}
        return not_found()

    def do_GET(self) -> None:
        self.answer("GET")

    def do_POST(self) -> None:
        self.answer("POST")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
