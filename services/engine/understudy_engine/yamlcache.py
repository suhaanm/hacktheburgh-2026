"""Parse a YAML file once per version of the file.

The role packs, their mapping, skills and task files, the connection registry and the evidence vocabulary were read and parsed with PyYAML (pure Python,
about 20 ms for a 350-node file) on every request: a screen that loads six routes parsed the same pack thirty times. ``load_yaml_file`` keeps the parsed
document as bytes (a pickle) keyed by the file's path, size and mtime_ns and hands every caller its own fresh copy, so a caller that edits what it got
cannot change what the next one gets, and an edit of the file is read at once. The parse itself is the same ``yaml.safe_load`` as before: identical results.
"""
from __future__ import annotations

import pickle
import threading
from pathlib import Path
from typing import Any

import yaml

_MAX = 512
_cache: dict[tuple[str, int, int], bytes] = {}
_lock = threading.Lock()
stats = {"hits": 0, "parses": 0}


def load_yaml_file(path: Path | str, *, encoding: str = "utf-8") -> Any:
    """``yaml.safe_load(Path(path).read_text(encoding))`` with the parse remembered per (path, size, mtime_ns). Raises what the plain call raises
    (OSError for a missing file, yaml.YAMLError for a bad one); a bad file is never remembered."""
    p = Path(path)
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    with _lock:
        blob = _cache.get(key)
    if blob is not None:
        stats["hits"] += 1
        return pickle.loads(blob)
    data = yaml.safe_load(p.read_text(encoding=encoding))
    try:
        blob = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:  # pragma: no cover - a document the pickle cannot hold is simply not remembered
        return data
    stats["parses"] += 1
    with _lock:
        for k in [k for k in _cache if k[0] == key[0]]:
            del _cache[k]                                   # an older version of this file
        if len(_cache) >= _MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = blob
    return pickle.loads(blob)                                # the caller's copy is never the stored one


def clear() -> None:
    with _lock:
        _cache.clear()
