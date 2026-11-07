"""Local model routes (LOC-1, LOC-2). ``api/app.py`` includes ``router`` only when this module imports and
``UNDERSTUDY_X_LOCALMODEL=1`` (or ``UNDERSTUDY_X=1``) is set.

  GET  /localmodel/status    {meta, data: {enabled, running, model: {file, size_bytes, sha_ok}, endpoint, tokens_per_s?, mode}}
  POST /localmodel/digest    internal, the worker's own app only: {task, items_ref} -> digests only (no input is echoed)

``items_ref`` is the name of a JSON or JSONL file under ``<data>/localmodel/items/`` that a source plugin wrote; raw items are
never accepted in a request body, never logged and never returned. The status call never starts the server and never hashes the
model inline (a missing hash is computed in the background once).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from .api.errors import ApiError
from .core import AnalyticMeta
from .localmodel import config
from .localmodel.server import get_server, model_check

router = APIRouter(tags=["localmodel"])
_LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")
_ALLOWED_ORIGIN_PREFIXES = ("http://localhost", "http://127.0.0.1", "tauri://", "app://", "file://")
_hash_thread: threading.Thread | None = None


def _meta(note: str) -> dict[str, Any]:
    return AnalyticMeta(origin="real", n=1, n_unit="runs", split=None, generated_at=datetime.now(timezone.utc), note=note
                        ).model_dump(mode="json")


def _verify_in_background() -> None:
    """If the model's SHA-256 has not been computed yet, compute it once on a daemon thread."""
    global _hash_thread
    if _hash_thread is not None and _hash_thread.is_alive():
        return
    if model_check(compute=False).sha_ok is not None:
        return
    _hash_thread = threading.Thread(target=lambda: model_check(compute=True), name="localmodel-sha", daemon=True)
    _hash_thread.start()


@router.get("/localmodel/status")
def localmodel_status(bench: bool = True):
    srv = get_server()
    if model_check(compute=False).exists and config.flag_on():
        _verify_in_background()
    data = srv.status(bench=bench)
    note = ("Qwen2.5-7B-Instruct Q4_K_M through llama.cpp on this Mac, loopback only. "
            + ("Using the model." if data["mode"] == "model" else f"Using the deterministic rules ({data['reason']})."))
    return {"meta": _meta(note), "data": data}


class DigestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: Literal["commit_digest", "event_digest"]
    items_ref: str


def _guard(request: Request) -> None:
    from .memory.store import WORKER_ACTORS

    host = request.client.host if request.client else ""
    if host not in _LOCAL_HOSTS:
        raise ApiError(403, "write_refused", "Digests can only be requested from this machine.")
    actor = request.headers.get("x-understudy-actor", "worker").strip()
    if actor not in WORKER_ACTORS:
        raise ApiError(403, "write_refused", f"Only the worker's own app can request digests; the actor {actor[:20]!r} cannot.")
    origin = request.headers.get("origin")
    if origin is not None and not origin.startswith(_ALLOWED_ORIGIN_PREFIXES):
        raise ApiError(403, "write_refused", "Digests are only requested from the Understudy app on this machine.")


def _load_items(ref: str) -> list[Any]:
    root = (config.data_dir() / "localmodel" / "items").resolve()
    if not ref or "/" in ref or "\\" in ref or ref.startswith("."):
        raise ApiError(422, "bad_items_ref", "items_ref is a file name under data/localmodel/items.")
    p = (root / ref).resolve()
    if root not in p.parents or not p.is_file():
        raise ApiError(404, "no_such_items", "No such items file.")
    text = p.read_text()
    try:
        if p.suffix == ".jsonl":
            return [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        v = json.loads(text)
        return v if isinstance(v, list) else [v]
    except ValueError:
        raise ApiError(422, "bad_items_file", "The items file is not valid JSON.")


@router.post("/localmodel/digest")
def localmodel_digest(body: DigestBody, request: Request):
    _guard(request)
    from .localmodel.digest import commit_digest_ex, event_digest_ex

    items = _load_items(body.items_ref)
    fn = commit_digest_ex if body.task == "commit_digest" else event_digest_ex
    try:
        batch = fn(items)
    except TypeError:
        raise ApiError(422, "bad_item", "Each item must be a string or an object.")
    return {"meta": _meta("Digests only: fixed vocabularies, booleans and buckets. No input text is returned."),
            "data": {"task": body.task, "n": len(batch.digests), "source": batch.source, "fallbacks": batch.fallbacks,
                     "digests": batch.digests}}
