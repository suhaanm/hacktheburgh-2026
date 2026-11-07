"""Shared plumbing for the Microsoft Graph sources (Outlook calendar, Teams meeting metadata).

**Off by default.** The Graph sources are not loadable through the registry unless ``UNDERSTUDY_GRAPH=1`` is set, they need
an injected ``token_provider`` (a zero-argument callable returning an access token; no MSAL here, the worker's own
sign-in lives outside this module), and every test uses recorded fake responses through an injected ``fetch``.

Safety properties, all tested:

* read only: the only HTTP method is GET, and ``default_fetch`` refuses anything but ``https://graph.microsoft.com``;
* a ``@odata.nextLink`` that points anywhere else is refused (no following a link to another host);
* the token is passed to ``fetch`` in a header and never stored, logged or put in an error;
* errors carry a code and a status number, never a response body.
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, tzinfo
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

from .base import SourceError
from .tz import local_to_utc, resolve_tz

UTC = timezone.utc
GRAPH_HOST = "graph.microsoft.com"
GRAPH_FLAG = "UNDERSTUDY_GRAPH"

Fetch = Callable[[str, dict[str, str]], dict]
TokenProvider = Callable[[], str]


class GraphHTTPError(Exception):
    """Raised by a ``fetch`` implementation on a non-2xx answer. Carries the status and Retry-After only."""

    def __init__(self, status: int, retry_after: float | None = None):
        super().__init__(f"graph http {status}")
        self.status, self.retry_after = status, retry_after


def graph_enabled() -> bool:
    return os.environ.get(GRAPH_FLAG, "").strip().lower() in ("1", "true", "yes")


def _check_url(url: str) -> None:
    u = urlparse(url)
    if u.scheme != "https" or u.hostname != GRAPH_HOST:
        raise SourceError("graph_url_refused", "only https://graph.microsoft.com is allowed")


def default_fetch(url: str, headers: dict[str, str]) -> dict:
    """The real transport: GET only, Graph host only. **Not used by any test and never called unless the owner enables
    the Graph source and supplies a token provider.**"""
    _check_url(url)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:        # noqa: S310 (host checked above)
            import json
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        ra = exc.headers.get("Retry-After") if exc.headers else None
        raise GraphHTTPError(exc.code, float(ra) if ra and ra.replace(".", "", 1).isdigit() else None) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SourceError("graph_unreachable") from None


class GraphClient:
    def __init__(self, token_provider: TokenProvider, fetch: Fetch | None = None, *, sleep: Callable[[float], None] = time.sleep,
                 max_pages: int = 100, max_retries: int = 3):
        if not callable(token_provider):
            raise SourceError("graph_no_token_provider", "a token provider is required")
        if fetch is None:
            if not graph_enabled():
                raise SourceError("graph_disabled", f"Graph sources are off; set {GRAPH_FLAG}=1 to enable them")
            fetch = default_fetch
        self._token, self._fetch, self._sleep = token_provider, fetch, sleep
        self._max_pages, self._max_retries = max_pages, max_retries

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json", "Prefer": 'outlook.timezone="UTC"'}

    def get(self, url: str) -> dict:
        _check_url(url)
        attempt = 0
        while True:
            try:
                data = self._fetch(url, self._headers())
            except GraphHTTPError as exc:
                if exc.status in (429, 503, 504) and attempt < self._max_retries:
                    attempt += 1
                    self._sleep(min(exc.retry_after if exc.retry_after is not None else 2.0 * attempt, 30.0))
                    continue
                if exc.status in (401, 403):
                    raise SourceError("graph_unauthorized", f"graph answered {exc.status}") from None
                raise SourceError(f"graph_http_{exc.status}", f"graph answered {exc.status}") from None
            if not isinstance(data, dict):
                raise SourceError("graph_bad_response")
            if "error" in data and "value" not in data:
                raise SourceError("graph_error_response")
            return data

    def pages(self, url: str) -> Iterator[list[dict]]:
        """Yield ``value`` lists page by page, following ``@odata.nextLink`` (same host only), up to ``max_pages``."""
        for _ in range(self._max_pages):
            data = self.get(url)
            value = data.get("value", [])
            yield value if isinstance(value, list) else []
            nxt = data.get("@odata.nextLink")
            if not nxt:
                return
            url = nxt
        raise SourceError("graph_too_many_pages")


def parse_graph_dt(obj: Any, default_tz: tzinfo = UTC) -> datetime | None:
    """``{"dateTime": "2026-11-02T09:00:00.0000000", "timeZone": "GMT Standard Time"}`` -> UTC datetime.

    Graph returns seven fractional digits; Python wants six. The zone is a Windows or IANA name; an unknown one falls
    back to ``default_tz`` (the caller counts it)."""
    if not isinstance(obj, dict):
        return None
    raw = obj.get("dateTime")
    if not isinstance(raw, str):
        return None
    s = raw.strip().replace("Z", "")
    if "." in s:
        head, frac = s.split(".", 1)
        s = f"{head}.{frac[:6]}"
    try:
        naive = datetime.fromisoformat(s)
    except ValueError:
        return None
    tz = resolve_tz(obj.get("timeZone")) or default_tz
    return naive.astimezone(UTC) if naive.tzinfo else local_to_utc(naive, tz)


def window(since: datetime | None, until: datetime | None, default_days: int = 28) -> tuple[datetime, datetime]:
    from datetime import timedelta
    u = until.astimezone(UTC) if until else datetime.now(UTC)
    s = since.astimezone(UTC) if since else u - timedelta(days=default_days)
    return s, u


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
