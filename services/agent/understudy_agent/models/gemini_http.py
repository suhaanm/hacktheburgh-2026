"""The only code in this package that talks to the Gemini HTTP API (REQ-5 phase C).

Two request paths behind one class, chosen by `api=` (env `GEMINI_API`, default `interactions`):

* `interactions`      POST /v1beta/interactions. The interface the vendor's current docs recommend. Verified live on 7 Nov 2026:
                      body {model, store:false, input:[{type:"text"},{type:"image",data,mime_type}], system_instruction,
                      generation_config:{thinking_level, max_output_tokens}, response_format:{type:"text", mime_type:
                      "application/json", schema}}; answer in steps[] (`model_output`), usage in total_input_tokens /
                      total_output_tokens / total_thought_tokens, status "completed" or "incomplete".
* `generate_content`  POST /v1beta/models/{model}:generateContent. Documented by the vendor as still supported ("legacy"). Verified
                      live on 7 Nov 2026: contents[].parts[] with inline_data, generationConfig.{responseMimeType,
                      responseJsonSchema, thinkingConfig.thinkingLevel, maxOutputTokens}; usage in usageMetadata.

Rules this file enforces for every path:

* the API key travels in the `x-goog-api-key` header only: never in a URL, a query string, a log line, a cache key or an error;
* every error message goes through `redact_text`; exceptions are raised `from None` so no transport object (and no request body)
  is attached; image bytes are only ever inside the request body;
* a hard per-call timeout (`httpx.Timeout`), no hidden retries (the router decides fallbacks, so latency and cost are what they say);
* `store: false` on the interactions path.
"""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from .config import ENV_GEMINI_KEY
from .errors import ConfigError, ModelRefusal, ProviderError
from .redact import redact_text
from .imaging import sniff_mime

BASE_URL = "https://generativelanguage.googleapis.com"
ENV_API = "GEMINI_API"            # interactions (default) | generate_content
ENV_API_REVISION = "GEMINI_API_REVISION"  # optional `Api-Revision` header for the interactions path; unset = not sent
ErrorKind = Literal["timeout", "network", "auth", "rate_limit", "api", "incomplete", "blocked", "empty"]


class GeminiHTTPError(ProviderError):
    """A failed Gemini call. `kind` is a closed set the router uses (breaker, escalation); `status` is the HTTP status if any."""

    def __init__(self, kind: ErrorKind, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.status = status


@dataclass(frozen=True)
class Part:
    """One input part: text, or image bytes (PNG or JPEG, already gated by the caller). Build with `Part.text` / `Part.image`.
    The bytes are hidden from `repr` so a log line or an assertion message can never carry them."""

    kind: Literal["text", "image"]
    value: str | bytes = field(repr=False)
    mime: str = ""

    @classmethod
    def text(cls, s: str) -> "Part":
        return cls("text", s)

    @classmethod
    def image(cls, data: bytes) -> "Part":
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise TypeError("an image part needs the image bytes")
        return cls("image", bytes(data), sniff_mime(bytes(data)))


@dataclass(frozen=True)
class GeminiReply:
    text: str
    input_tokens: int | None
    output_tokens: int | None      # visible output only
    thought_tokens: int | None     # billed as output
    latency_ms: int
    api: str
    model: str
    finish: str | None
    calls: tuple[dict[str, Any], ...] = ()    # function calls the model asked for (computer use): {id, name, arguments}
    cached_input_tokens: int | None = None    # input tokens served from the provider's prompt cache (None = not reported)
    image_tokens: int | None = None           # input tokens spent on images (None = not reported)

    @property
    def billed_output_tokens(self) -> int | None:
        if self.output_tokens is None:
            return None
        return self.output_tokens + (self.thought_tokens or 0)


def _int(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _image_tokens(details: Any, token_key: str) -> int | None:
    """Sum of the IMAGE modality entries in a usage breakdown ([{modality, tokens|tokenCount}]); None when there is no breakdown."""
    if not isinstance(details, list):
        return None
    vals = [_int(d.get(token_key)) for d in details if isinstance(d, dict) and str(d.get("modality", "")).lower() == "image"]
    return sum(v for v in vals if v is not None) if vals else (0 if details else None)


class GeminiClient:
    def __init__(self, *, api_key: str | None = None, api: str | None = None, base_url: str = BASE_URL,
                 timeout_s: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        key = (api_key if api_key is not None else os.environ.get(ENV_GEMINI_KEY, "")).strip()
        if not key:
            raise ConfigError("GEMINI_API_KEY is not set. Add it to .env (never commit it) and start the service with the "
                              "environment loaded, or leave UNDERSTUDY_X_GEMINI off.")
        self._key = key
        self.api = (api or os.environ.get(ENV_API, "").strip() or "interactions").lower()
        if self.api not in ("interactions", "generate_content"):
            raise ConfigError("GEMINI_API must be 'interactions' or 'generate_content'")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._http = httpx.Client(transport=transport, timeout=httpx.Timeout(timeout_s), follow_redirects=False)

    # ------------------------------------------------------------------ plumbing
    def __repr__(self) -> str:  # never show the key
        return f"GeminiClient(api={self.api!r}, base_url={self.base_url!r})"

    def _headers(self) -> dict[str, str]:
        h = {"x-goog-api-key": self._key, "Content-Type": "application/json"}
        rev = os.environ.get(ENV_API_REVISION, "").strip()
        if rev and self.api == "interactions":
            h["Api-Revision"] = rev
        return h

    def _redact(self, text: object, max_chars: int = 300) -> str:
        return redact_text(text, max_chars=max_chars, extra_secrets=(self._key,))

    def _error_from_response(self, r: httpx.Response) -> GeminiHTTPError:
        status = r.status_code
        detail = ""
        try:
            j = r.json()
            err = j.get("error") if isinstance(j, dict) else None
            if isinstance(err, dict):
                detail = f"{err.get('status', '')}: {err.get('message', '')}"
        except ValueError:
            detail = r.text[:200]
        kind: ErrorKind = "auth" if status in (401, 403) else "rate_limit" if status == 429 else "api"
        return GeminiHTTPError(kind, f"gemini {kind} (HTTP {status}): {self._redact(detail)}", status)

    def _post(self, url: str, body: dict[str, Any], timeout_s: float | None) -> tuple[dict[str, Any], int]:
        t0 = time.perf_counter()
        try:
            r = self._http.post(url, headers=self._headers(), json=body,
                                timeout=httpx.Timeout(timeout_s) if timeout_s else httpx.USE_CLIENT_DEFAULT)
        except httpx.TimeoutException:
            ms = round((time.perf_counter() - t0) * 1000)
            raise GeminiHTTPError("timeout", f"gemini call timed out after {ms} ms") from None
        except httpx.HTTPError as e:
            raise GeminiHTTPError("network", f"gemini network error ({type(e).__name__})") from None
        ms = round((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            raise self._error_from_response(r)
        try:
            j = r.json()
        except ValueError:
            raise GeminiHTTPError("api", "gemini returned a body that is not JSON", r.status_code) from None
        if not isinstance(j, dict):
            raise GeminiHTTPError("api", "gemini returned an unexpected body", r.status_code)
        return j, ms

    # ------------------------------------------------------------------ generation
    def generate(self, model: str, parts: list[Part], *, system: str | None = None, schema: dict[str, Any] | None = None,
                 thinking: str | None = "low", max_output_tokens: int = 1024, timeout_s: float | None = None,
                 tools: list[dict[str, Any]] | None = None) -> GeminiReply:
        if not model:
            raise ConfigError("no Gemini model id configured")
        if self.api == "interactions":
            return self._interactions(model, parts, system, schema, thinking, max_output_tokens, timeout_s, tools)
        if tools:
            raise ProviderError("the computer-use tool is only wired on the interactions API (set GEMINI_API=interactions)")
        return self._generate_content(model, parts, system, schema, thinking, max_output_tokens, timeout_s)

    @staticmethod
    def _b64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    def _interactions(self, model: str, parts: list[Part], system: str | None, schema: dict[str, Any] | None,
                      thinking: str | None, max_out: int, timeout_s: float | None,
                      tools: list[dict[str, Any]] | None = None) -> GeminiReply:
        inp: list[dict[str, Any]] = []
        for p in parts:
            if p.kind == "text":
                inp.append({"type": "text", "text": str(p.value)})
            else:
                assert isinstance(p.value, bytes)
                inp.append({"type": "image", "data": self._b64(p.value), "mime_type": p.mime})
        body: dict[str, Any] = {"model": model, "store": False, "input": inp}
        if system:
            body["system_instruction"] = system
        gen: dict[str, Any] = {"max_output_tokens": max_out}
        if thinking:
            gen["thinking_level"] = thinking
        body["generation_config"] = gen
        if schema is not None:
            body["response_format"] = {"type": "text", "mime_type": "application/json", "schema": schema}
        if tools:
            body["tools"] = tools
        j, ms = self._post(f"{self.base_url}/v1beta/interactions", body, timeout_s)
        status = j.get("status")
        text = "".join(c.get("text", "") for s in j.get("steps") or [] if isinstance(s, dict) and s.get("type") == "model_output"
                       for c in s.get("content") or [] if isinstance(c, dict) and c.get("type") == "text")
        calls = tuple({"id": str(s.get("id", "")), "name": str(s.get("name", "")), "arguments": s.get("arguments") or {}}
                      for s in j.get("steps") or [] if isinstance(s, dict) and s.get("type") == "function_call")
        u = j.get("usage") or {}
        reply = GeminiReply(text=text, input_tokens=_int(u.get("total_input_tokens")), output_tokens=_int(u.get("total_output_tokens")),
                            thought_tokens=_int(u.get("total_thought_tokens")), latency_ms=ms, api="interactions", model=model,
                            finish=str(status) if status else None, calls=calls, cached_input_tokens=_int(u.get("total_cached_tokens")),
                            image_tokens=_image_tokens(u.get("input_tokens_by_modality"), "tokens"))
        if status == "incomplete":
            raise GeminiHTTPError("incomplete", "gemini answer was cut off at the output token limit")
        if status in ("failed", "cancelled"):
            raise GeminiHTTPError("api", f"gemini interaction status {self._redact(status, 40)}")
        if not text and not calls:
            raise GeminiHTTPError("empty", "gemini returned no text")
        return reply

    def _generate_content(self, model: str, parts: list[Part], system: str | None, schema: dict[str, Any] | None,
                          thinking: str | None, max_out: int, timeout_s: float | None) -> GeminiReply:
        ps: list[dict[str, Any]] = []
        for p in parts:
            if p.kind == "text":
                ps.append({"text": str(p.value)})
            else:
                assert isinstance(p.value, bytes)
                ps.append({"inline_data": {"mime_type": p.mime, "data": self._b64(p.value)}})
        gen: dict[str, Any] = {"maxOutputTokens": max_out}
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = schema
        if thinking:
            gen["thinkingConfig"] = {"thinkingLevel": thinking}
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": ps}], "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        j, ms = self._post(f"{self.base_url}/v1beta/models/{model}:generateContent", body, timeout_s)
        pf = j.get("promptFeedback") or {}
        if pf.get("blockReason"):
            raise ModelRefusal(f"gemini blocked the prompt ({self._redact(pf.get('blockReason'), 60)})")
        cands = j.get("candidates") or []
        if not cands:
            raise GeminiHTTPError("empty", "gemini returned no candidates")
        c0 = cands[0] if isinstance(cands[0], dict) else {}
        finish = c0.get("finishReason")
        text = "".join(p.get("text", "") for p in (c0.get("content") or {}).get("parts") or []
                       if isinstance(p, dict) and not p.get("thought"))
        u = j.get("usageMetadata") or {}
        reply = GeminiReply(text=text, input_tokens=_int(u.get("promptTokenCount")), output_tokens=_int(u.get("candidatesTokenCount")),
                            thought_tokens=_int(u.get("thoughtsTokenCount")) or 0, latency_ms=ms, api="generate_content",
                            model=model, finish=str(finish) if finish else None,
                            cached_input_tokens=_int(u.get("cachedContentTokenCount")),
                            image_tokens=_image_tokens(u.get("promptTokensDetails"), "tokenCount"))
        if finish == "MAX_TOKENS":
            raise GeminiHTTPError("incomplete", "gemini answer was cut off at the output token limit")
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"):
            raise ModelRefusal(f"gemini declined to answer ({self._redact(finish, 40)})")
        if not text:
            raise GeminiHTTPError("empty", "gemini returned no text")
        return reply

    # ------------------------------------------------------------------ models.list
    def list_models(self, *, timeout_s: float = 20.0) -> dict[str, list[str]]:
        """{model id without the 'models/' prefix: [supported generation methods]} for every model the key can see."""
        out: dict[str, list[str]] = {}
        token: str | None = None
        for _ in range(20):  # 61 models at the time of writing; the cap only guards against a paging loop
            params: dict[str, Any] = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            try:
                r = self._http.get(f"{self.base_url}/v1beta/models", headers=self._headers(), params=params,
                                   timeout=httpx.Timeout(timeout_s))
            except httpx.TimeoutException:
                raise GeminiHTTPError("timeout", "gemini models.list timed out") from None
            except httpx.HTTPError as e:
                raise GeminiHTTPError("network", f"gemini network error ({type(e).__name__})") from None
            if r.status_code != 200:
                raise self._error_from_response(r)
            try:
                j = r.json()
            except ValueError:
                raise GeminiHTTPError("api", "gemini models.list returned a body that is not JSON", r.status_code) from None
            for m in j.get("models") or []:
                name = str(m.get("name", ""))
                out[name.removeprefix("models/")] = [str(x) for x in m.get("supportedGenerationMethods") or []]
            token = j.get("nextPageToken")
            if not token:
                break
        return out

    def close(self) -> None:
        self._http.close()
