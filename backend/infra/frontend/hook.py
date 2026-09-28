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
MAX_BODY = 5 * 1024 * 1024          # GitHub caps a delivery at 25 MB; a push is far smaller
LOG = "/srv/redeploy.log"

_lock = threading.Lock()
_state = {"running": False, "pending": False, "last": ""}


def _log(line: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{stamp} {line}", flush=True)


def _run_builds() -> None:
    while True:
        with _lock:
            if not _state["pending"]:
                _state["running"] = False
                return
            _state["pending"] = False
        with open(LOG, "a", encoding="utf-8") as out:
            result = subprocess.run(["/opt/hook/redeploy.sh"], stdout=out, stderr=subprocess.STDOUT,
                                    check=False)
        _state["last"] = "ok" if result.returncode == 0 else f"failed ({result.returncode})"
        _log(f"redeploy {_state['last']}")


def _trigger() -> str:
    with _lock:
        _state["pending"] = True
        if _state["running"]:
            return "queued behind the running build"
        _state["running"] = True
    threading.Thread(target=_run_builds, daemon=True).start()
    return "started"


class Hook(BaseHTTPRequestHandler):
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
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._answer(413, {"error": "body size"})
            return
        body = self.rfile.read(length)
        expected = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, self.headers.get("X-Hub-Signature-256", "")):
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
