"""The GitHub webhook receiver for the frontend on the staging box.

POST /hooks/github. It acts only when GitHub's X-Hub-Signature-256 matches the
shared secret, and only on a push to the deploy branch; then it runs redeploy.sh.
One build at a time: a push that arrives during a build queues one more run
after it, never two. Nothing from the request reaches a command line; the
script pulls the branch itself.

GET /hooks/health answers 200, and says whether a build is running.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["WEBHOOK_SECRET"].encode()
BRANCH = os.environ.get("DEPLOY_BRANCH", "integration")
MAX_BODY = 1024 * 1024              # a push payload lists at most 20 commits; well under this
LOG = "/srv/redeploy.log"

_lock = threading.Lock()
_state = {"running": False, "pending": False, "last": ""}


def _log(line: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{stamp} {line}", flush=True)


def _build_once() -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as out:
            result = subprocess.run(["/opt/hook/redeploy.sh"], stdout=out,
                                    stderr=subprocess.STDOUT, check=False)
        _state["last"] = "ok" if result.returncode == 0 else f"failed ({result.returncode})"
    except Exception as exc:  # a full disk or a missing script must not wedge the queue
        _state["last"] = f"error: {exc}"
    _log(f"redeploy {_state['last']}")


def _run_builds() -> None:
    try:
        while True:
            with _lock:
                if not _state["pending"]:
                    return
                _state["pending"] = False
            _build_once()
    finally:
        with _lock:
            _state["running"] = False
            again = _state["pending"]
        if again:
            _trigger()


def _trigger() -> str:
    with _lock:
        _state["pending"] = True
        if _state["running"]:
            return "queued behind the running build"
        _state["running"] = True
    threading.Thread(target=_run_builds, daemon=True).start()
    return "started"


class Hook(BaseHTTPRequestHandler):
    # the body is read before the signature can be checked: a client that sends
    # a length and then stalls gives up its thread after this many seconds
    timeout = 10

    def _answer(self, status: int, body: dict[str, object]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/hooks/health":
            self._answer(200, {"ok": True, "running": _state["running"], "last": _state["last"]})
            return
        self._answer(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/hooks/github":
            self._answer(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._answer(400, {"error": "length"})
            return
        if length <= 0 or length > MAX_BODY:
            self._answer(413, {"error": "body size"})
            return
        body = self.rfile.read(length)
        expected = ("sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()).encode()
        given = self.headers.get("X-Hub-Signature-256", "").encode("utf-8", "replace")
        if len(body) != length or not hmac.compare_digest(expected, given):
            _log("refused: bad signature")
            self._answer(401, {"error": "signature"})
            return
        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            self._answer(200, {"ok": True, "pong": True})
            return
        if event != "push":
            self._answer(202, {"ignored": event})
            return
        try:
            ref = json.loads(body).get("ref", "")
        except ValueError:
            self._answer(400, {"error": "json"})
            return
        if ref != f"refs/heads/{BRANCH}":
            self._answer(202, {"ignored": ref})
            return
        outcome = _trigger()
        _log(f"push to {BRANCH}: {outcome}")
        self._answer(202, {"deploy": outcome})

    def log_message(self, fmt: str, *args: object) -> None:
        _log(fmt % args)


if __name__ == "__main__":
    _log(f"listening on :9000 for pushes to {BRANCH}")
    ThreadingHTTPServer(("0.0.0.0", 9000), Hook).serve_forever()
