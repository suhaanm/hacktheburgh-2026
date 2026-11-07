"""Boot check (NFR-3): the configured model ids must be usable by the key. Never prints a key.

    uv run --env-file .env python -m understudy_agent.models.boot            # OpenAI, and Gemini when a key or ids are set
    uv run --env-file .env python -m understudy_agent.models.boot --list     # also print every usable id

OpenAI: `models.list` against OPENAI_MODEL_PLANNER / _FAST / _COMPUTER_USE. Gemini (REQ-5): `GET /v1beta/models` against
GEMINI_MODEL_FAST / _ACCURATE / _LIVE (a fast or accurate id must support generateContent, a live id bidiGenerateContent). A wrong id
stops with the list of usable ids; an id is never guessed. `boot_check()` (called at service start) also checks Gemini when
UNDERSTUDY_X_GEMINI is on; with the flag off nothing about Gemini runs. Mock mode makes no network call at all.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import (ENV_COMPUTER, ENV_FAST, ENV_GEMINI_ACCURATE, ENV_GEMINI_FAST, ENV_GEMINI_LIVE, GeminiModelIds, ModelIds,
                     gemini_flag_enabled, gemini_key_present, mock_enabled)
from .errors import ConfigError, ProviderError
from .redact import redact_text

_RELEVANT = re.compile(r"^(gpt|o\d|computer|chatgpt)", re.I)


@dataclass
class BootReport:
    ok: bool
    mock: bool
    configured: dict[str, str] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)  # role -> configured id that the key cannot use
    usable: list[str] = field(default_factory=list)
    message: str = ""
    provider: str = "openai"


# The last result of each provider's check in this process, for models_status(). Ids and booleans only.
LAST_BOOT: dict[str, dict[str, Any]] = {}


def _remember(rep: "BootReport") -> "BootReport":
    LAST_BOOT[rep.provider] = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": rep.ok, "mock": rep.mock,
                               "configured": dict(rep.configured), "missing": dict(rep.missing)}
    return rep


def list_usable_models(client: Any) -> list[str]:
    return sorted(m.id for m in client.models.list().data)


def boot_check(*, client: Any | None = None, raise_on_fail: bool = True, out: Callable[[str], None] = print,
               gemini_client: Any | None = None) -> BootReport:
    """In mock mode this is a no-op that makes no network call. Otherwise it lists the models the key can use
    and, if a configured id is missing, prints the usable ids and stops with instructions. When UNDERSTUDY_X_GEMINI is on the
    Gemini ids are checked too (same loud failure)."""
    rep = _openai_boot_check(client=client, raise_on_fail=raise_on_fail, out=out)
    if mock_enabled() or not gemini_flag_enabled():
        return rep
    if not rep.ok:
        return rep   # the OpenAI failure already printed and (if asked) stopped
    grep = gemini_boot_check(client=gemini_client, raise_on_fail=raise_on_fail, out=out)
    return rep if grep.ok else grep


def _openai_boot_check(*, client: Any | None = None, raise_on_fail: bool = True,
                       out: Callable[[str], None] = print) -> BootReport:
    if mock_enabled():
        return BootReport(ok=True, mock=True, message="mock mode: no models checked")
    try:
        ids = ModelIds.from_env()
    except ConfigError as e:
        msg = str(e)
        out(msg)
        if raise_on_fail:
            raise SystemExit(msg) from e
        return BootReport(ok=False, mock=False, message=msg)
    if client is None:
        import openai

        try:
            client = openai.OpenAI(timeout=30, max_retries=1)
        except openai.OpenAIError as e:
            msg = "OPENAI_API_KEY is not set. Add it to .env (never commit it), or set UNDERSTUDY_MOCK=1."
            out(msg)
            if raise_on_fail:
                raise SystemExit(msg) from e
            return BootReport(ok=False, mock=False, configured=ids.as_dict(), message=msg)
    try:
        usable = list_usable_models(client)
    except Exception as e:  # network, auth, quota: say so without leaking anything
        msg = f"Could not list models ({type(e).__name__}). Check the key, network and quota."
        out(msg)
        if raise_on_fail:
            raise SystemExit(msg) from e
        return BootReport(ok=False, mock=False, configured=ids.as_dict(), message=msg)
    have = set(usable)
    missing = {role: mid for role, mid in ids.as_dict().items() if mid not in have}
    if not missing:
        return BootReport(ok=True, mock=False, configured=ids.as_dict(), usable=usable,
                          message="all configured models are usable")
    envs = {"planner": ENV_PLANNER, "fast": ENV_FAST, "computer_use": ENV_COMPUTER}
    lines = ["The key cannot use these configured models:"]
    lines += [f"  {envs[r]}={m}" for r, m in missing.items()]
    relevant = [m for m in usable if _RELEVANT.match(m)]
    lines.append("Usable model ids (gpt, o-series, computer):")
    lines += [f"  {m}" for m in relevant]
    lines.append("Edit .env so each OPENAI_MODEL_* is one of the ids above, then start again. Ids are never guessed.")
    msg = "\n".join(lines)
    out(msg)
    if raise_on_fail:
        raise SystemExit(msg)
    return BootReport(ok=False, mock=False, configured=ids.as_dict(), missing=missing, usable=usable, message=msg)


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv

        load_dotenv()  # the app loads .env itself; harmless if already loaded
    except Exception:
        pass
    rep = boot_check(raise_on_fail=False)
    print(f"mock={rep.mock} ok={rep.ok} configured={rep.configured}")
    sys.exit(0 if rep.ok else 1)
