"""The library over real HTTP, with no test framework, on both clients: a token,
a read, a write retried after a 503 with the same Idempotency-Key, two pages,
a 404, a real timeout and a real refused connection.

    python tests/smoke/smoke.py

It starts tests/smoke/server.py on a free port and stops it at the end.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from reeds import APIConnectionError, APIConnectionTimeoutError, AsyncReeds, NotFoundError, Reeds


def check(ok: bool, what: str) -> None:
    if not ok:
        print(f"smoke FAILED: {what}", file=sys.stderr)
        raise SystemExit(1)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def calls(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text().splitlines() if line]


def check_log(log: Path, reference: str) -> None:
    entries = calls(log)
    posts = [e for e in entries if e["method"] == "POST" and e["path"] == "/shipping/v1/deliveries"]
    check(len(posts) == 2, f"{reference}: the 503 was retried")
    check(posts[0]["key"] is not None and posts[0]["key"] == posts[1]["key"], f"{reference}: the retry reused the Idempotency-Key")
    check(len([e for e in entries if e["path"] == "/oauth/token"]) == 1, f"{reference}: one token for every call")
    check(all(e["auth"] == "Bearer tok_smoke" for e in entries if e["path"] != "/oauth/token"), f"{reference}: every call carried the token")


def sync_run(base_url: str, refused_url: str) -> None:
    with Reeds(client_id="rci_test_smoke", client_secret="rcs_test_smoke", base_url=base_url) as reeds:
        check(reeds.mode == "test", "sync: mode")
        coverage = reeds.shipping.coverage.get()
        check(coverage.states is not None and coverage.states[0].state == "Lagos", "sync: coverage")
        made = reeds.shipping.deliveries.create(quote_id="qt_1", reference="SYNC", ready=True)
        check(made.id == "dlv_1" and made.reference == "SYNC" and made.model_extra == {"quote_id": "qt_1"}, "sync: create")
        check([d.id for d in reeds.shipping.deliveries.list(limit=2)] == ["dlv_3", "dlv_2", "dlv_1"], "sync: pagination")
        try:
            reeds.shipping.deliveries.get("dlv_x")
            check(False, "sync: a 404 raises")
        except NotFoundError as error:
            check(error.code == "NOT_FOUND" and error.request_id == "req_smoke", "sync: the 404's code and request id")
        started = time.monotonic()
        try:
            reeds.shipping.wallet.get(timeout=0.3, max_retries=0)
            check(False, "sync: a slow answer times out")
        except APIConnectionTimeoutError as error:
            check(error.code == "TIMEOUT" and time.monotonic() - started < 1.5, "sync: the timeout")
    with Reeds(client_id="rci_test_smoke", client_secret="rcs_test_smoke", base_url=refused_url, max_retries=0) as nobody:
        try:
            nobody.shipping.coverage.get()
            check(False, "sync: no server raises")
        except APIConnectionError as error:
            check(not isinstance(error, APIConnectionTimeoutError) and error.code == "CONNECTION_FAILED", "sync: a refused connection")


async def async_run(base_url: str, refused_url: str) -> None:
    async with AsyncReeds(client_id="rci_test_smoke", client_secret="rcs_test_smoke", base_url=base_url) as reeds:
        coverage = await reeds.shipping.coverage.get()
        check(coverage.states is not None and coverage.states[0].state == "Lagos", "async: coverage")
        made = await reeds.shipping.deliveries.create(quote_id="qt_1", reference="ASYNC", ready=True)
        check(made.id == "dlv_1", "async: create")
        check([d.id async for d in reeds.shipping.deliveries.list(limit=2)] == ["dlv_3", "dlv_2", "dlv_1"], "async: pagination")
        first = await reeds.shipping.deliveries.list(limit=2)
        check([d.id for d in first.data] == ["dlv_3", "dlv_2"] and first.has_more, "async: the first page")
        try:
            await reeds.shipping.deliveries.get("dlv_x")
            check(False, "async: a 404 raises")
        except NotFoundError as error:
            check(error.code == "NOT_FOUND" and error.request_id == "req_smoke", "async: the 404's code and request id")
        try:
            await reeds.shipping.wallet.get(timeout=0.3, max_retries=0)
            check(False, "async: a slow answer times out")
        except APIConnectionTimeoutError as error:
            check(error.code == "TIMEOUT", "async: the timeout")
    async with AsyncReeds(client_id="rci_test_smoke", client_secret="rcs_test_smoke", base_url=refused_url, max_retries=0) as nobody:
        try:
            await nobody.shipping.coverage.get()
            check(False, "async: no server raises")
        except APIConnectionError as error:
            check(not isinstance(error, APIConnectionTimeoutError) and error.code == "CONNECTION_FAILED", "async: a refused connection")


def main() -> None:
    port, refused = free_port(), free_port()
    base_url, refused_url = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{refused}"
    with tempfile.TemporaryDirectory() as directory:
        log = Path(directory) / "calls.log"
        server = subprocess.Popen([sys.executable, str(Path(__file__).with_name("server.py")), str(port)], env={**os.environ, "REEDS_SMOKE_LOG": str(log)})
        try:
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            sync_run(base_url, refused_url)
            check_log(log, "sync")
            log.unlink()
            asyncio.run(async_run(base_url, refused_url))
            check_log(log, "async")
        finally:
            server.terminate()
            server.wait()
    print(f"smoke ok on Python {sys.version.split()[0]}")


if __name__ == "__main__":
    main()
