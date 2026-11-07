"""A stand-in for ``llama-server`` used by the hermetic tests (LOC-1): ``python -m understudy_engine.localmodel.stub_server``.

It accepts the flags the real server is started with (and ignores the ones it does not need), binds only where told to, serves
``GET /health`` and ``POST /v1/chat/completions`` (OpenAI shape, honours the Bearer key from ``--api-key-file``), and answers
from the deterministic rules, or misbehaves on purpose so the guards and the fallbacks can be tested without 4.7 GB of weights.

Behaviour comes from the file ``<data>/localmodel/stub_behaviour`` (found relative to ``--api-key-file``, because the real
launcher passes no environment through), read on every request: ``rules`` (default), ``garbage`` (not JSON), ``leak`` (a field holds the input text),
``badenum`` (a value outside the vocabulary), ``extra_key`` (an extra field holding input text), ``slow`` (never answers in
time), ``flaky`` (the first call per process fails with a 500), ``pii`` (an email in a field). It logs no request content.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import rules

_calls = {"n": 0}
_lock = threading.Lock()


def _answer(task: str, payload: dict[str, Any], behaviour: str, keys: list[str] | None = None) -> Any:
    if task == "commit":
        item = {"message": payload.get("message", ""), "files": [{"path": p} for p in payload.get("paths", [])],
                "additions": payload.get("lines_added", 0), "deletions": payload.get("lines_deleted", 0)}
        full = rules.digest_commit(item)
        out: dict[str, Any] = {k: full[k] for k in ("category", "risk", "message_quality") if keys is None or k in keys}
        text = str(payload.get("message", ""))
    else:
        item = {"title": payload.get("title", ""), "description": payload.get("description", ""),
                "attendees": payload.get("attendees", 0), "duration_min": payload.get("duration_minutes"),
                "recurring": payload.get("recurring", False)}
        full = rules.digest_event(item)
        out = {k: full[k] for k in ("category", "needs_prep") if keys is None or k in keys}
        text = str(payload.get("title", ""))
    if behaviour == "leak":
        out["category"] = text
    elif behaviour == "badenum":
        out["category"] = "banana"
    elif behaviour == "extra_key":
        out["note"] = text
    elif behaviour == "pii":
        out["category"] = "jane.doe@example.com"
    return out


def make_handler(api_key: str | None, behaviour_file: Path | None) -> type[BaseHTTPRequestHandler]:
    def current() -> str:
        try:
            return behaviour_file.read_text().strip() if behaviour_file else "rules"
        except OSError:
            return "rules"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a: Any) -> None:            # never log request content
            return

        def _send(self, code: int, obj: Any) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                return self._send(200, {"status": "ok"})
            if api_key and self.headers.get("Authorization") != f"Bearer {api_key}":
                return self._send(401, {"error": "unauthorised"})
            self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            if api_key and self.headers.get("Authorization") != f"Bearer {api_key}":
                return self._send(401, {"error": "unauthorised"})
            if self.path != "/v1/chat/completions":
                return self._send(404, {"error": "not found"})
            behaviour = current()
            with _lock:
                _calls["n"] += 1
                first = _calls["n"] == 1
            if behaviour == "flaky" and first:
                return self._send(500, {"error": "warming up"})
            if behaviour == "slow":
                time.sleep(30)
            try:
                req = json.loads(raw)
                msgs = req["messages"]
                task = "commit" if "git commits" in msgs[0]["content"] else "event"
                payload = json.loads(msgs[-1]["content"])
            except (ValueError, KeyError, IndexError, TypeError):
                return self._send(400, {"error": "bad request"})
            if behaviour == "garbage":
                content = "I think this is a bug fix."
            else:
                try:
                    keys = list(req["response_format"]["json_schema"]["schema"]["properties"])
                except (KeyError, TypeError):
                    keys = None
                content = json.dumps(_answer(task, payload, behaviour, keys))
            self._send(200, {
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                          "prompt_tokens_details": {"cached_tokens": 0}},
                "timings": {"predicted_per_second": 25.0},
            })

    return Handler


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8089)
    ap.add_argument("--api-key-file", default=None)
    args, _unknown = ap.parse_known_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("the stub only binds loopback")
    key = None
    if args.api_key_file:
        key = Path(args.api_key_file).read_text().strip() or None
    bfile = Path(args.api_key_file).parent.parent / "localmodel" / "stub_behaviour" if args.api_key_file else None
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(key, bfile))
    srv.daemon_threads = True
    srv.serve_forever()


if __name__ == "__main__":
    main()
