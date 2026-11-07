"""Per-install salt and label/domain hashing (CAP-4).

Identifiers (UI labels, domains) are never stored in the clear. They are replaced by
``h:<hex>`` / ``d:<hex>``: an HMAC-SHA256 under a secret per-install salt, truncated.
The salt lives in ``$UNDERSTUDY_HOME/salt`` (mode 600) and never leaves the device.
Synthetic data uses a fixed, public salt so regeneration is deterministic.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlsplit

from .paths import home_dir

SYNTHETIC_SALT = b"understudy-synthetic-salt-v1"
HEX_LEN = 12

_salt_cache: dict[str, bytes] = {}


def salt_path():
    return home_dir() / "salt"


def get_salt(create: bool = True) -> bytes:
    """Return the per-install salt, creating it (atomically, mode 600) if missing."""
    path = salt_path()
    key = str(path)
    if key in _salt_cache:
        return _salt_cache[key]
    if path.exists():
        salt = bytes.fromhex(path.read_text().strip())
    elif not create:
        raise FileNotFoundError(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(32)
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(salt.hex())
        try:
            os.link(tmp, path)  # fails if another process won the race
        except FileExistsError:
            salt = bytes.fromhex(path.read_text().strip())
        finally:
            os.unlink(tmp)
    _salt_cache[key] = salt
    return salt


def _mac(kind: bytes, value: str, salt: bytes | None) -> str:
    salt = get_salt() if salt is None else salt
    return hmac.new(salt, kind + b"\x00" + value.encode("utf-8"), hashlib.sha256).hexdigest()[:HEX_LEN]


def hash_label(label: str, salt: bytes | None = None) -> str:
    """``h:<hex>`` for a UI label. Case and whitespace insensitive."""
    norm = re.sub(r"\s+", " ", label.strip().lower())
    return "h:" + _mac(b"label", norm, salt)


def hash_domain(host_or_url: str, salt: bytes | None = None) -> str:
    """``d:<hex>`` for a domain. Accepts a bare host or a URL; drops port, path and ``www.``."""
    s = host_or_url.strip().lower()
    host = urlsplit(s if "//" in s else "//" + s).hostname or s
    if host.startswith("www."):
        host = host[4:]
    return "d:" + _mac(b"domain", host, salt)
