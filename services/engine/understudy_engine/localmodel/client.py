"""OpenAI-compatible client for the local llama-server (LOC-1). Loopback only; returns parsed objects, never raw text.

Constrained output uses the OpenAI-style ``response_format = {"type": "json_schema", ...}``, which the installed llama.cpp
(build 11960) turns into a grammar; the model cannot emit anything outside the schema. Verified on this machine against the
real model (see ``docs``/the evaluation's ``meta``). No proxy settings are honoured (``trust_env=False``) and a URL whose host
is not loopback is refused, so nothing in this module can reach another machine.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config


class ClientError(Exception):
    """A request failed after the retry. ``kind`` is a short stable token; the message never carries prompt text."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


@dataclass
class ChatResult:
    obj: dict[str, Any]
    seconds: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_s: float | None        # llama.cpp's own generation speed for this call, when reported
    cached_prompt_tokens: int = 0


def assert_loopback(base_url: str) -> str:
    host = urlparse(base_url).hostname or ""
    if host not in config.LOOPBACK_HOSTS:
        raise ClientError("not_loopback", "the local model client only talks to this machine")
    return base_url.rstrip("/")


class LocalClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout_s: float | None = None, retries: int | None = None):
        self.base_url = assert_loopback(base_url)
        self.api_key = api_key
        self.timeout_s = config.LIMITS.timeout_s if timeout_s is None else timeout_s
        self.retries = config.LIMITS.retries if retries is None else retries
        self._http = httpx.Client(timeout=self.timeout_s, trust_env=False)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def healthy(self, timeout_s: float = 1.5) -> bool:
        try:
            r = self._http.get(f"{self.base_url}/health", timeout=timeout_s)
            return r.status_code == 200 and r.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def chat_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        name: str = "digest",
        max_tokens: int | None = None,
        temperature: float | None = None,
        seed: int = 7,
    ) -> ChatResult:
        """One constrained completion. Retries once on a transport error, a server error or an unparseable reply."""
        body = {
            "model": "local",
            "messages": messages,
            "temperature": config.LIMITS.temperature if temperature is None else temperature,
            "top_k": 1,
            "seed": seed,
            "max_tokens": config.LIMITS.max_tokens if max_tokens is None else max_tokens,
            "cache_prompt": True,
            "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        }
        last: ClientError | None = None
        for attempt in range(self.retries + 1):
            t0 = time.perf_counter()
            try:
                r = self._http.post(f"{self.base_url}/v1/chat/completions", json=body, headers=self._headers())
            except httpx.TimeoutException:
                last = ClientError("timeout")
                continue
            except httpx.HTTPError as exc:
                last = ClientError("transport", type(exc).__name__)
                continue
            if r.status_code in (401, 403):
                raise ClientError("unauthorised")                       # not retried: the key is wrong
            if r.status_code >= 500 or r.status_code == 429:
                last = ClientError("server_error", str(r.status_code))
                time.sleep(0.2)
                continue
            if r.status_code != 200:
                raise ClientError("rejected", str(r.status_code))
            try:
                payload = r.json()
                choice = payload["choices"][0]
                if choice.get("finish_reason") == "length":
                    last = ClientError("truncated")
                    continue
                obj = json.loads(choice["message"]["content"])
                if not isinstance(obj, dict):
                    raise ValueError("not an object")
            except (ValueError, KeyError, IndexError, TypeError):
                last = ClientError("unparseable")
                continue
            usage = payload.get("usage") or {}
            timings = payload.get("timings") or {}
            tps = timings.get("predicted_per_second")
            return ChatResult(
                obj=obj,
                seconds=time.perf_counter() - t0,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                tokens_per_s=float(tps) if isinstance(tps, (int, float)) else None,
                cached_prompt_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
            )
        assert last is not None
        raise last
