"""Boot check (NFR-3): the configured model ids must be usable by the key. Never prints the key.

    uv run --env-file .env python -m understudy_agent.models.boot
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import ENV_COMPUTER, ENV_FAST, ENV_PLANNER, ModelIds, mock_enabled
from .errors import ConfigError

_RELEVANT = re.compile(r"^(gpt|o\d|computer|chatgpt)", re.I)


@dataclass
class BootReport:
    ok: bool
    mock: bool
    configured: dict[str, str] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)  # role -> configured id that the key cannot use
    usable: list[str] = field(default_factory=list)
    message: str = ""


def list_usable_models(client: Any) -> list[str]:
    return sorted(m.id for m in client.models.list().data)


def boot_check(*, client: Any | None = None, raise_on_fail: bool = True,
               out: Callable[[str], None] = print) -> BootReport:
    """In mock mode this is a no-op that makes no network call. Otherwise it lists the models the key can use
    and, if a configured id is missing, prints the usable ids and stops with instructions."""
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
