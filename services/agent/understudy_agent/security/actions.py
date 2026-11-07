"""Layer 3: typed one-step actions (SEC-3).

The model can only ask for an action from a fixed, typed set with validated arguments. One action per step, each
authorised by exactly one fresh observation, inside a step cap and a deadline. Anything else is rejected before an
actuator sees it. No model call; pure code.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from .labels import canonical_keys
from .sanitize import strip_invisible

# ------------------------------------------------------------------ errors


class ActionRejected(ValueError):
    """The proposed action is not a valid typed action. `code` is a short stable reason for the audit log."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BudgetExceeded(RuntimeError):
    def __init__(self, which: str, message: str) -> None:
        super().__init__(message)
        self.which = which  # "steps" | "deadline"


class StaleObservation(RuntimeError):
    pass


# ------------------------------------------------------------------ the typed action set

DESKTOP_KINDS = ("click", "double_click", "move", "drag", "scroll", "type", "key", "wait", "screenshot")
BROWSER_KINDS = ("goto", "click_element", "fill", "select_option", "press", "scroll_page", "wait_for", "extract", "back")
ALL_KINDS = DESKTOP_KINDS + BROWSER_KINDS

MAX_TYPE_CHARS = 500
MAX_PATH_POINTS = 32
MAX_SCROLL = 5000
MAX_WAIT_S = 10.0
MAX_URL_CHARS = 2000
MAX_SELECTOR_CHARS = 300

_MODIFIERS = {"ctrl", "alt", "shift", "cmd"}
_MODIFIER_INPUT = {"ctrl", "control", "ctl", "alt", "option", "opt", "shift", "cmd", "command", "meta", "super", "win", "windows"}
_NAMED_KEYS = {
    "enter", "return", "tab", "esc", "escape", "space", "backspace", "delete", "del", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown", "page_up", "page_down", *(f"f{i}" for i in range(1, 13)),
}
_SINGLE_KEY = re.compile(r"^[A-Za-z0-9`~!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|]$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BUTTONS = {"left", "right"}


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _need(args: dict[str, Any], keys: Iterable[str], optional: Iterable[str] = ()) -> None:
    keys, optional = set(keys), set(optional)
    missing = keys - set(args)
    if missing:
        raise ActionRejected("missing_arg", f"missing argument(s): {', '.join(sorted(missing))}")
    extra = set(args) - keys - optional
    if extra:
        raise ActionRejected("unknown_arg", f"unexpected argument(s): {', '.join(sorted(extra))}")


def _coord(args: dict[str, Any], name: str, limit: int | None) -> int:
    v = args.get(name)
    if not _is_int(v):
        raise ActionRejected("bad_coordinate", f"{name} must be an integer")
    if v < 0 or (limit is not None and v >= limit):
        raise ActionRejected("coordinate_off_screen", f"{name}={v} is outside the screen")
    return v


def _hold_keys(args: dict[str, Any]) -> list[str] | None:
    hk = args.get("hold_keys")
    if hk is None:
        return None
    if not isinstance(hk, list) or len(hk) > 4 or not all(isinstance(k, str) and k.lower() in _MODIFIER_INPUT for k in hk):
        raise ActionRejected("bad_hold_keys", "hold_keys must be a short list of modifier names")
    return [k.lower() for k in hk]


def _label_hint(args: dict[str, Any]) -> str | None:
    v = args.get("label")
    if v is None:
        return None
    if not isinstance(v, str) or len(v) > 120:
        raise ActionRejected("bad_label", "label hint must be a short string")
    return v


def _clean_text(v: Any, name: str, limit: int = MAX_TYPE_CHARS, allow_empty: bool = False) -> str:
    if not isinstance(v, str):
        raise ActionRejected("bad_text", f"{name} must be a string")
    if not v and not allow_empty:
        raise ActionRejected("empty_text", f"{name} must not be empty")
    if len(v) > limit:
        raise ActionRejected("text_too_long", f"{name} is longer than {limit} characters")
    if _CONTROL.search(v):
        raise ActionRejected("control_chars", f"{name} contains control characters")
    cleaned, removed = strip_invisible(v)
    if removed:
        raise ActionRejected("invisible_chars", f"{name} contains invisible characters")
    return v


def _check_selector(args: dict[str, Any]) -> dict[str, Any]:
    sel, role, name = args.get("selector"), args.get("role"), args.get("name")
    if sel is not None:
        _clean_text(sel, "selector", MAX_SELECTOR_CHARS)
        if role is not None or name is not None:
            raise ActionRejected("ambiguous_target", "give selector or role+name, not both")
        return {"selector": sel}
    if role is not None and name is not None:
        _clean_text(role, "role", 40)
        _clean_text(name, "name", 200)
        return {"role": role, "name": name}
    raise ActionRejected("missing_target", "give selector or role and name")


def _check_url(url: Any) -> str:
    u = _clean_text(url, "url", MAX_URL_CHARS)
    try:
        p = urlsplit(u)
    except ValueError as e:
        raise ActionRejected("bad_url", "unparseable url") from e
    if u != "about:blank" and p.scheme not in ("http", "https"):
        raise ActionRejected("bad_url_scheme", "only http and https addresses are allowed")
    if p.username or p.password:
        raise ActionRejected("url_credentials", "addresses with embedded credentials are not allowed")
    if u != "about:blank" and not p.hostname:
        raise ActionRejected("bad_url", "address has no host")
    return u


def _check_keys(keys: Any) -> list[str]:
    if not isinstance(keys, list) or not 1 <= len(keys) <= 4 or not all(isinstance(k, str) for k in keys):
        raise ActionRejected("bad_keys", "keys must be a list of 1 to 4 key names")
    out = []
    for k in keys:
        kl = k.strip().lower()
        if kl in _MODIFIER_INPUT or kl in _NAMED_KEYS or _SINGLE_KEY.match(k.strip()):
            out.append(k.strip() if len(k.strip()) == 1 else kl)
        else:
            raise ActionRejected("unknown_key", f"unknown key name {k[:20]!r}")
    return out


@dataclass(frozen=True)
class ValidatedAction:
    kind: str
    args: dict[str, Any]
    signature: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "args": self.args}


def validate_action(kind: str, args: dict[str, Any] | None = None, *,
                    screen: tuple[int, int] | None = None) -> ValidatedAction:
    """Return a normalised ValidatedAction or raise ActionRejected. `screen` is (width, height) in the pixel space of
    the screenshot the action was derived from; when given, coordinates outside it are rejected."""
    if isinstance(kind, (list, tuple)):
        raise ActionRejected("batch_not_allowed", "one action per step")
    if kind not in ALL_KINDS:
        raise ActionRejected("unknown_kind", f"unknown action kind {str(kind)[:30]!r}")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ActionRejected("bad_args", "args must be an object")
    w, h = screen if screen else (None, None)
    out: dict[str, Any]

    if kind in ("click", "double_click"):
        _need(args, ["x", "y"], ["button", "hold_keys", "label"])
        btn = args.get("button", "left")
        if btn not in _BUTTONS:
            raise ActionRejected("bad_button", "only left and right buttons are allowed")
        if kind == "double_click" and btn != "left":
            raise ActionRejected("bad_button", "double click uses the left button")
        out = {"x": _coord(args, "x", w), "y": _coord(args, "y", h)}
        if kind == "click":
            out["button"] = btn
        if (hk := _hold_keys(args)):
            out["hold_keys"] = hk
        if (lb := _label_hint(args)) is not None:
            out["label"] = lb
    elif kind == "move":
        _need(args, ["x", "y"], ["hold_keys"])
        out = {"x": _coord(args, "x", w), "y": _coord(args, "y", h)}
        if (hk := _hold_keys(args)):
            out["hold_keys"] = hk
    elif kind == "drag":
        _need(args, ["path"], ["hold_keys"])
        path = args["path"]
        if not isinstance(path, list) or not 2 <= len(path) <= MAX_PATH_POINTS:
            raise ActionRejected("bad_path", f"path needs 2 to {MAX_PATH_POINTS} points")
        pts = []
        for p in path:
            if not isinstance(p, dict) or set(p) != {"x", "y"}:
                raise ActionRejected("bad_path", "path points are {x, y}")
            pts.append({"x": _coord(p, "x", w), "y": _coord(p, "y", h)})
        out = {"path": pts}
        if (hk := _hold_keys(args)):
            out["hold_keys"] = hk
    elif kind == "scroll":
        _need(args, ["x", "y", "scroll_x", "scroll_y"], ["hold_keys"])
        out = {"x": _coord(args, "x", w), "y": _coord(args, "y", h)}
        for n in ("scroll_x", "scroll_y"):
            v = args[n]
            if not _is_int(v) or abs(v) > MAX_SCROLL:
                raise ActionRejected("bad_scroll", f"{n} must be an integer within +-{MAX_SCROLL}")
            out[n] = v
        if (hk := _hold_keys(args)):
            out["hold_keys"] = hk
    elif kind == "type":
        _need(args, ["text"])
        out = {"text": _clean_text(args["text"], "text")}
    elif kind == "key":
        _need(args, ["keys"])
        out = {"keys": _check_keys(args["keys"])}
    elif kind == "wait":
        _need(args, [], ["seconds"])
        out = {}
        if "seconds" in args:
            s = args["seconds"]
            if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 <= s <= MAX_WAIT_S:
                raise ActionRejected("bad_wait", f"seconds must be between 0 and {MAX_WAIT_S:g}")
            out["seconds"] = s
    elif kind == "screenshot":
        _need(args, [])
        out = {}
    elif kind == "goto":
        _need(args, ["url"])
        out = {"url": _check_url(args["url"])}
    elif kind == "click_element":
        _need(args, [], ["selector", "role", "name", "label"])
        out = _check_selector({k: v for k, v in args.items() if k != "label"})
        if (lb := _label_hint(args)) is not None:
            out["label"] = lb
    elif kind == "fill":
        _need(args, [], ["selector", "role", "name", "value", "param"])
        tgt = _check_selector({k: v for k, v in args.items() if k not in ("value", "param")})
        if ("value" in args) == ("param" in args):
            raise ActionRejected("fill_source", "give exactly one of value or param")
        if "value" in args:
            tgt["value"] = _clean_text(args["value"], "value", allow_empty=True)
        else:
            if not isinstance(args["param"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,63}", args["param"]):
                raise ActionRejected("bad_param", "param must be a plain parameter name")
            tgt["param"] = args["param"]
        out = tgt
    elif kind == "select_option":
        _need(args, ["value"], ["selector", "role", "name"])
        out = _check_selector({k: v for k, v in args.items() if k != "value"})
        out["value"] = _clean_text(args["value"], "value", 200)
    elif kind == "press":
        _need(args, ["keys"])
        out = {"keys": _check_keys(args["keys"])}
    elif kind == "scroll_page":
        _need(args, ["dy"])
        v = args["dy"]
        if not _is_int(v) or abs(v) > MAX_SCROLL:
            raise ActionRejected("bad_scroll", f"dy must be an integer within +-{MAX_SCROLL}")
        out = {"dy": v}
    elif kind == "wait_for":
        _need(args, [], ["selector", "text", "timeout_s"])
        if ("selector" in args) == ("text" in args):
            raise ActionRejected("wait_target", "give exactly one of selector or text")
        out = {}
        if "selector" in args:
            out["selector"] = _clean_text(args["selector"], "selector", MAX_SELECTOR_CHARS)
        else:
            out["text"] = _clean_text(args["text"], "text", 200)
        t = args.get("timeout_s", 5)
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 < t <= MAX_WAIT_S * 6:
            raise ActionRejected("bad_wait", "timeout_s out of range")
        out["timeout_s"] = t
    elif kind == "extract":
        _need(args, ["name", "selector"])
        if not isinstance(args["name"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", args["name"]):
            raise ActionRejected("bad_name", "name must be a plain identifier")
        out = {"name": args["name"], "selector": _clean_text(args["selector"], "selector", MAX_SELECTOR_CHARS)}
    else:  # back
        _need(args, [])
        out = {}
    return ValidatedAction(kind, out, action_signature(kind, out))


def validate_model_action(action: Any, *, screen: tuple[int, int] | None = None) -> ValidatedAction:
    """Validate anything with .kind and .args (e.g. the port's Action). A list or tuple is a batch and is rejected."""
    if isinstance(action, (list, tuple)):
        raise ActionRejected("batch_not_allowed", "one action per step")
    kind = getattr(action, "kind", None)
    args = getattr(action, "args", None)
    if kind is None and isinstance(action, dict):
        kind, args = action.get("kind"), action.get("args")
    if kind is None:
        raise ActionRejected("not_an_action", "not an action")
    return validate_action(kind, args, screen=screen)


# ------------------------------------------------------------------ signature (shared with the stuck-loop detector)

SIGNATURE_BUCKET_PX = 24


def action_signature(kind: str, args: dict[str, Any]) -> str:
    """Canonical comparable form: coordinates in coarse buckets; typed text hashed (never stored); labels ignored."""
    b = SIGNATURE_BUCKET_PX
    sig: dict[str, Any] = {"k": kind}
    for n in ("x", "y"):
        if n in args:
            sig[n] = args[n] // b
    if "path" in args:
        sig["path"] = [[p["x"] // b, p["y"] // b] for p in args["path"]]
    for n in ("scroll_x", "scroll_y", "dy"):
        if n in args:
            sig[n] = (args[n] // 100) * 100
    if "text" in args:
        sig["t"] = hashlib.sha256(args["text"].encode()).hexdigest()[:10]
    if "value" in args:
        sig["v"] = hashlib.sha256(str(args["value"]).encode()).hexdigest()[:10]
    if "keys" in args:
        sig["keys"] = canonical_keys(args["keys"])
    for n in ("url", "selector", "role", "name", "param", "button"):
        if n in args:
            sig[n] = args[n]
    return json.dumps(sig, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------ budgets and fresh observations


class StepBudget:
    """A step cap and a wall-clock deadline for one run or navigator. `clock` is injectable for tests."""

    def __init__(self, max_steps: int = 20, deadline_s: float = 600.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_steps = max_steps
        self.deadline_s = deadline_s
        self._clock = clock
        self._start = clock()
        self.steps = 0

    def elapsed(self) -> float:
        return self._clock() - self._start

    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.steps)

    def check(self) -> None:
        """Raise if the next step would exceed a budget. Does not consume a step."""
        if self.steps >= self.max_steps:
            raise BudgetExceeded("steps", f"step cap of {self.max_steps} reached")
        if self.elapsed() >= self.deadline_s:
            raise BudgetExceeded("deadline", f"deadline of {self.deadline_s:g}s reached")

    def tick(self) -> int:
        self.check()
        self.steps += 1
        return self.steps


@dataclass(frozen=True)
class ObservationToken:
    id: int
    t: float


class ObservationClock:
    """Each observation authorises exactly ONE action and only while fresh. The loop is observe, then act, then
    observe again; an action built from an older observation (or reused) is refused."""

    def __init__(self, max_age_s: float = 30.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_age_s = max_age_s
        self._clock = clock
        self._lock = threading.Lock()
        self._next = 0
        self._current: ObservationToken | None = None
        self._spent = True

    def new_observation(self) -> ObservationToken:
        with self._lock:
            self._next += 1
            self._current = ObservationToken(self._next, self._clock())
            self._spent = False
            return self._current

    def authorise(self, token: ObservationToken | None) -> None:
        with self._lock:
            if token is None or self._current is None or token.id != self._current.id:
                raise StaleObservation("action was not built from the latest observation")
            if self._spent:
                raise StaleObservation("this observation already authorised an action; observe again")
            if self._clock() - token.t > self.max_age_s:
                raise StaleObservation(f"observation is older than {self.max_age_s:g}s; observe again")
            self._spent = True
