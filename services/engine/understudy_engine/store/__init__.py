"""Event store: validated append-only JSONL, pure fold, replay, hashing (CAP-2 to CAP-4)."""
from .fold import Frame, Replay, State, TaskState, fold, replay, step
from .hashing import SYNTHETIC_SALT, get_salt, hash_domain, hash_label
from .jsonl import AppendResult, EventStore, OriginMixError, StoreError
from .paths import data_dir, home_dir, is_mock, repo_root
from .validate import InvalidEvent, fmt_t, parse_t, to_row, validate_row

__all__ = [
    "AppendResult", "EventStore", "Frame", "InvalidEvent", "OriginMixError", "Replay", "State",
    "StoreError", "SYNTHETIC_SALT", "TaskState", "data_dir", "fmt_t", "fold", "get_salt", "hash_domain",
    "hash_label", "home_dir", "is_mock", "parse_t", "repo_root", "replay", "step", "to_row", "validate_row",
]
