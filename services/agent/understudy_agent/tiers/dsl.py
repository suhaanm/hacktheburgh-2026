"""Tier 1: the compiled JSON step DSL and its interpreter (AGT-3, HND-3).

A bundle is data, never code. Model-generated code is never executed; a model may only DRAFT a bundle,
and `validate_bundle` plus a dry run decide whether it is accepted (see compile.py).

Steps: goto, click(selector | role+name), fill(selector, value), select(selector, value),
       wait_for(selector), assert_text(selector, contains), extract(name, selector), checkpoint(name).
Each step may carry `pre` and `post` condition lists:
       {"visible": sel} {"exists": sel} {"absent": sel} {"text_contains": {"selector", "value"}}
       {"url_contains": "..."} {"value_equals": {"selector", "value"}}
Values: {"param": name, "mul"?: float, "round"?: int} or {"literal": text}.
A failed precondition raises PreconditionFailed: the navigator escalates to tier 2 from where it is.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .base import Emit, GateStop, PostconditionFailed, PreconditionFailed, StepBudgetExceeded, StepEvent
from .safety import Guard

OPS = {"goto", "click", "fill", "select", "wait_for", "assert_text", "extract", "checkpoint"}
CONDITION_KEYS = {"visible", "exists", "absent", "text_contains", "url_contains", "value_equals", "title_contains",
                  "page_text", "page_text_absent"}
MAX_STEPS = 60
STEP_KEYS = {"id", "op", "url", "url_param", "selector", "role", "name", "value", "contains", "timeout_ms", "pre",
             "post", "optional", "note", "pattern", "as", "resumable", "irreversible", "text", "url_contains"}


# ----------------------------------------------------------------------------- validation
def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    """Static checks only (structure, ops, params). The selector and dry-run checks live in compile.py."""
    errs: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle must be an object"]
    if is_platform_bundle(bundle):
        try:
            bundle = to_internal(bundle)
        except (KeyError, TypeError) as exc:
            return [f"malformed bundle: {exc!r}"[:120]]
    for k in ("id", "version", "steps", "params"):
        if k not in bundle:
            errs.append(f"missing key {k!r}")
    steps = bundle.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["steps must be a non-empty list"]
    if len(steps) > MAX_STEPS:
        errs.append(f"too many steps ({len(steps)} > {MAX_STEPS})")
    declared = set(bundle.get("params", []))
    seen_ids: set[str] = set()
    for i, s in enumerate(steps):
        where = f"step {i}"
        if not isinstance(s, dict):
            errs.append(f"{where}: must be an object")
            continue
        sid = s.get("id", f"s{i}")
        where = f"step {sid}"
        if sid in seen_ids:
            errs.append(f"{where}: duplicate id")
        seen_ids.add(sid)
        extra = set(s) - STEP_KEYS
        if extra:
            errs.append(f"{where}: unknown keys {sorted(extra)}")
        op = s.get("op")
        if op not in OPS:
            errs.append(f"{where}: unknown op {op!r}")
            continue
        if op == "goto":
            u = str(s.get("url", ""))
            if s.get("url_param"):
                if s["url_param"] not in declared:
                    errs.append(f"{where}: undeclared url_param {s['url_param']!r}")
            elif not (u.startswith("{base}") or re.fullmatch(r"https?://[A-Za-z0-9._:/?=&%#-]+", u)):
                errs.append(f"{where}: goto url must start with {{base}} or be an http(s) address")
        if op in ("click", "fill", "select", "wait_for", "assert_text", "extract"):
            ok_target = s.get("selector") or (op in ("click", "fill", "select") and s.get("role") and s.get("name")) \
                or (op == "wait_for" and (s.get("text") or s.get("url_contains"))) \
                or (op == "assert_text" and s.get("contains"))
            if not ok_target:
                errs.append(f"{where}: needs a selector" + (" or role+name" if op in ("click", "fill", "select") else ""))
        if op in ("fill", "select"):
            errs += _check_value(s.get("value"), declared, where)
        if op == "assert_text":
            errs += _check_value(s.get("contains"), declared, where)
        if op == "wait_for" and s.get("text") is not None:
            errs += _check_value(s.get("text"), declared, where)
        if op == "extract" and not s.get("name"):
            errs.append(f"{where}: extract needs a name")
        if op == "checkpoint" and not s.get("name"):
            errs.append(f"{where}: checkpoint needs a name")
        for phase in ("pre", "post"):
            for cond in s.get(phase, []) or []:
                if not isinstance(cond, dict) or len(set(cond) & CONDITION_KEYS) != 1:
                    errs.append(f"{where}: bad {phase} condition {cond!r}")
                    continue
                for k, v in cond.items():
                    if k in ("page_text", "page_text_absent"):
                        errs += _check_value(v.get("value") if isinstance(v, dict) else None, declared, f"{where} {phase}")
                    elif k in ("text_contains", "value_equals"):
                        if not isinstance(v, dict) or "selector" not in v:
                            errs.append(f"{where}: {phase}.{k} needs selector")
                        else:
                            errs += _check_value(v.get("value"), declared, f"{where} {phase}")
    return errs


def _check_value(v: Any, declared: set[str], where: str) -> list[str]:
    if not isinstance(v, dict) or len(set(v) & {"param", "literal"}) != 1:
        return [f"{where}: value must be {{param}} or {{literal}}"]
    if "param" in v and v["param"] not in declared:
        return [f"{where}: undeclared param {v['param']!r}"]
    if "param" in v and set(v) - {"param", "mul", "round"}:
        return [f"{where}: unknown value keys {sorted(set(v) - {'param', 'mul', 'round'})}"]
    return []


def bundle_params(bundle: dict[str, Any]) -> set[str]:
    return set(bundle.get("params", []))



# ----------------------------------------------------------------------------- platform bundle format
# packages/schema/steps.schema.json is the shared contract (engine, extension, compile step). The interpreter runs
# it natively by converting it to the internal form above.
def is_platform_bundle(b: Any) -> bool:
    return isinstance(b, dict) and b.get("schema") == 1 and isinstance(b.get("params"), dict)


def _val(spec: dict[str, Any], decls: dict[str, Any]) -> dict[str, Any]:
    if "literal" in spec:
        return {"literal": spec["literal"]}
    out: dict[str, Any] = {"param": spec["param"]}
    t = decls.get(spec["param"], {}).get("transform")
    if t:
        out.update({"mul": float(t["mul"]), "round": int(t.get("round", 2))})
    return out


def _conds(cond: dict[str, Any] | None, decls: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for k, v in (cond or {}).items():
        if k == "always":
            continue
        if k == "selector_visible":
            out.append({"visible": v})
        elif k == "selector_absent":
            out.append({"absent": v})
        elif k in ("url_contains", "title_contains"):
            out.append({k: v})
        elif k == "text_contains":
            out.append({"page_text": {"value": _val(v, decls)}})
        elif k == "text_absent":
            out.append({"page_text_absent": {"value": _val(v, decls)}})
        elif k == "field_equals":
            out.append({"value_equals": {"selector": v["selector"], "value": _val({"param": v["param"]}, decls)}})
    return out


def to_internal(b: dict[str, Any]) -> dict[str, Any]:
    decls = b["params"]
    steps: list[dict[str, Any]] = []
    for st in b["steps"]:
        op = st["op"]
        s: dict[str, Any] = {"id": st["id"], "op": op, "pre": _conds(st.get("precondition"), decls),
                             "post": _conds(st.get("postcondition"), decls)}
        for k in ("selector", "role", "name", "url", "url_param", "timeout_ms", "url_contains", "pattern", "as", "note"):
            if k in st:
                s[k] = st[k]
        if st.get("irreversible"):
            s["irreversible"] = True
        if op == "fill":
            s["value"] = _val({"param": st["param"]}, decls)
        elif op == "select":
            s["value"] = _val({"param": st["param"]}, decls) if "param" in st else {"literal": st["option"]}
        elif op == "assert_text":
            s["contains"] = {"param": st["param"]} if "param" in st else {"literal": st["literal"]}
            if "param" in st:
                s["contains"] = _val({"param": st["param"]}, decls)
        elif op == "wait_for" and "text" in st:
            s["text"] = _val(st["text"], decls)
        elif op == "extract":
            s["name"] = st["name"]
        elif op == "checkpoint":
            s["name"] = st["name"]
            if st.get("resumable"):
                s["resumable"] = True
        steps.append(s)
    return {"id": b["id"], "version": 1, "params": list(decls), "param_decls": decls,
            "never": list(b.get("never", [])), "steps": steps, "platform": True}


def param_defaults(b: dict[str, Any]) -> dict[str, str]:
    return {k: str(v["default"]) for k, v in (b.get("param_decls") or {}).items() if v.get("default") is not None}


def goto_hosts(b: dict[str, Any]) -> set[str]:
    """Hosts a bundle navigates to: its recorded sites (data-flow layer 5 only; never limits navigation)."""
    from urllib.parse import urlsplit

    hosts: set[str] = set()
    decls = b.get("param_decls") or {}
    for s in b.get("steps", []):
        if s.get("op") != "goto":
            continue
        u = s.get("url") or ""
        if s.get("url_param") and decls.get(s["url_param"], {}).get("default"):
            u = str(decls[s["url_param"]]["default"])
        if u.startswith("http"):
            sp = urlsplit(u)
            hosts.add(f"{sp.hostname}:{sp.port}" if sp.port else str(sp.hostname))
    return hosts

# ----------------------------------------------------------------------------- values
class MissingParam(KeyError):
    pass


def resolve_value(spec: dict[str, Any], params: dict[str, str]) -> str:
    if "literal" in spec:
        return str(spec["literal"])
    name = spec["param"]
    if name not in params:
        raise MissingParam(name)
    v = params[name]
    if "mul" in spec and v != "":
        nd = int(spec.get("round", 2))
        return f"{round(float(v) * float(spec['mul']), nd):.{nd}f}"
    return v


# ----------------------------------------------------------------------------- interpreter
@dataclass
class DslResult:
    outputs: dict[str, str] = field(default_factory=dict)
    steps_run: int = 0
    checkpoints: list[str] = field(default_factory=list)
    last_step_id: str = ""
    stopped_before: str = ""        # id of an irreversible step the run stopped in front of (dry runs, shadow mode)


@dataclass
class DslRuntime:
    page: Any
    params: dict[str, str]
    base_url: str
    query: str = ""
    navigator: str = "nav"
    emit: Emit | None = None
    guard: Guard | None = None
    is_current: Callable[[], bool] = lambda: True
    step_start: int = 0
    step_cap: int = MAX_STEPS
    pre_timeout_ms: int = 2000
    post_timeout_ms: int = 5000
    run_id: str | None = None
    stop_before_irreversible: bool = False
    never: list[str] = field(default_factory=list)   # phrases the bundle must never click (from bundle["never"])


async def _label_of(loc: Any) -> tuple[str, str]:
    return await loc.evaluate(
        """e => { const tag = e.tagName.toLowerCase();
                  const label = e.getAttribute('aria-label') || ((tag === 'input' && ['submit','button'].includes(e.type)) ? e.value : '')
                                || e.innerText || e.getAttribute('title') || '';
                  return [label.trim(), e.getAttribute('role') || tag]; }"""
    )


def _locator(page: Any, step: dict[str, Any]) -> Any:
    if step.get("selector"):
        return page.locator(step["selector"])
    return page.get_by_role(step["role"], name=step["name"], exact=True)


async def _cond_failure(rt: DslRuntime, conds: list[dict[str, Any]], timeout_ms: int) -> str | None:
    page = rt.page
    for c in conds or []:
        key = next(iter(set(c) & CONDITION_KEYS))
        v = c[key]
        try:
            if key == "visible":
                await page.locator(v).first.wait_for(state="visible", timeout=timeout_ms)
            elif key == "exists":
                await page.locator(v).first.wait_for(state="attached", timeout=timeout_ms)
            elif key == "absent":
                await page.locator(v).first.wait_for(state="detached", timeout=timeout_ms)
            elif key == "url_contains":
                await page.wait_for_url(lambda u, want=v: want in u, timeout=timeout_ms)
            elif key == "title_contains":
                deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
                while v not in await page.title():
                    if asyncio.get_event_loop().time() > deadline:
                        return f"title_contains {v}"
                    await asyncio.sleep(0.05)
            elif key in ("page_text", "page_text_absent"):
                want = resolve_value(v["value"], rt.params)
                deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
                while True:
                    body = await page.locator("body").inner_text(timeout=timeout_ms)
                    present = want in body
                    if present == (key == "page_text"):
                        break
                    if asyncio.get_event_loop().time() > deadline:
                        return f"{key}"
                    await asyncio.sleep(0.05)
            elif key == "text_contains":
                want = resolve_value(v["value"], rt.params)
                loc = page.locator(v["selector"]).first
                await loc.wait_for(state="attached", timeout=timeout_ms)
                got = await loc.inner_text(timeout=timeout_ms)
                if want not in got:
                    return f"text_contains {v['selector']}"
            elif key == "value_equals":
                want = resolve_value(v["value"], rt.params)
                got = await page.locator(v["selector"]).first.input_value(timeout=timeout_ms)
                if got != want:
                    return f"value_equals {v['selector']}"
        except Exception as exc:  # noqa: BLE001 - Playwright timeouts and detaches are all failed conditions
            if isinstance(exc, MissingParam):
                raise
            return f"{key} {v if isinstance(v, str) else (v.get('selector', '') if isinstance(v, dict) else '')}"
    return None


async def run_bundle(bundle: dict[str, Any], rt: DslRuntime) -> DslResult:
    errs = validate_bundle(bundle)
    if errs:
        raise ValueError("invalid bundle: " + "; ".join(errs[:3]))
    if is_platform_bundle(bundle):
        bundle = to_internal(bundle)
    rt.params = {**param_defaults(bundle), **rt.params}
    rt.never = [str(x).lower() for x in bundle.get("never", [])]
    res = DslResult()
    n = rt.step_start
    for idx, step in enumerate(bundle["steps"]):
        sid = step.get("id", f"s{idx}")
        if not rt.is_current():
            raise asyncio.CancelledError()
        if res.steps_run >= rt.step_cap:
            raise StepBudgetExceeded(f"bundle step cap {rt.step_cap}")
        n += 1
        op = step["op"]
        if step.get("irreversible") and rt.stop_before_irreversible:
            res.stopped_before = sid
            return res
        timeout_pre = int(step.get("timeout_ms", rt.pre_timeout_ms))
        fail = await _cond_failure(rt, step.get("pre", []), timeout_pre)
        if fail:
            _emit(rt, n, op, False, f"{sid} pre {fail}")
            raise PreconditionFailed(sid, fail)
        try:
            await _do_step(rt, step, sid, res, timeout_pre)
        except (PreconditionFailed, GateStop):
            _emit(rt, n, op, False, f"{sid} blocked")
            raise
        fail = await _cond_failure(rt, step.get("post", []), rt.post_timeout_ms)
        if fail:
            _emit(rt, n, op, False, f"{sid} post {fail}")
            raise PostconditionFailed(sid, fail)
        res.steps_run += 1
        res.last_step_id = sid
        _emit(rt, n, op, True, sid)
    return res


def _emit(rt: DslRuntime, n: int, op: str, ok: bool, detail: str) -> None:
    ev = StepEvent(navigator=rt.navigator, step=n, tier=1, action=op, ok=ok, detail=detail)
    if rt.guard:
        rt.guard.record_step(ev)
    if rt.emit:
        rt.emit(ev)


def typed_action(rt: DslRuntime, step: dict[str, Any], label: str | None, url: str | None = None) -> dict[str, Any]:
    """The step as one of agent-safety's typed actions (layer 3). The value of a `param` is never shown to it."""
    op = step["op"]
    if op == "goto":
        return {"kind": "goto", "args": {"url": url}}
    if op in ("wait_for", "assert_text", "extract") and not step.get("selector"):
        if op == "wait_for" and step.get("text") is not None:
            return {"kind": "wait_for", "args": {"text": resolve_value(step["text"], rt.params)[:200] or " ",
                                                 "timeout_s": max(0.5, int(step.get("timeout_ms", rt.post_timeout_ms)) / 1000)}}
        if op == "wait_for":
            return {"kind": "wait_for", "args": {"text": str(step.get("url_contains", "page"))[:200],
                                                 "timeout_s": max(0.5, int(step.get("timeout_ms", rt.post_timeout_ms)) / 1000)}}
        return {"kind": "extract", "args": {"name": step.get("name", "assert_text"), "selector": "body"}}
    target = {"selector": step["selector"]} if step.get("selector") else {"role": step["role"], "name": step["name"]}
    if op == "click":
        hint = ((label or "") + (" (submit)" if step.get("irreversible") else "")).strip()
        return {"kind": "click_element", "args": {**target, **({"label": hint[:120]} if hint else {})}}
    if op == "fill":
        v = step["value"]
        return {"kind": "fill", "args": {**target, **({"param": v["param"]} if "param" in v else {"value": v["literal"]})}}
    if op == "select":
        return {"kind": "select_option", "args": {**target, "value": resolve_value(step["value"], rt.params)}}
    if op == "wait_for":
        return {"kind": "wait_for", "args": {"selector": step["selector"],
                                             "timeout_s": max(0.5, int(step.get("timeout_ms", rt.post_timeout_ms)) / 1000)}}
    return {"kind": "extract", "args": {"name": step.get("name", "assert_text"), "selector": step["selector"]}}


async def _do_step(rt: DslRuntime, step: dict[str, Any], sid: str, res: DslResult, timeout_ms: int) -> None:
    page, op = rt.page, step["op"]
    if op == "checkpoint":
        res.checkpoints.append(step["name"])
        return
    n = rt.step_start + res.steps_run + 1
    url = None
    if op == "goto":
        raw = rt.params[step["url_param"]] if step.get("url_param") else step["url"]
        url = raw.replace("{base}", rt.base_url.rstrip("/"))
        if rt.query and "?" not in url:
            url += rt.query
    no_target = op == "goto" or (not step.get("selector") and not (step.get("role") and step.get("name")))
    loc = None if no_target else _locator(page, step)
    label, role = None, None
    if op in ("click", "fill", "select"):
        try:
            await loc.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            raise PreconditionFailed(sid, f"target not visible: {step.get('selector') or step.get('name')}") from None
        if await loc.count() != 1:
            raise PreconditionFailed(sid, f"target is not unique ({await loc.count()} matches)")
        label, role = await _label_of(loc)
        if op == "click" and any(n and n in (label or "").lower() for n in rt.never):
            from types import SimpleNamespace

            raise GateStop(SimpleNamespace(verdict="block", layer="never", codes=["bundle_never"], queue_id=None,
                                           reasons=["the routine says it must never do this"]), label or sid)
    dec = None
    if rt.guard:  # observe -> authorise (one fresh observation authorises exactly this one action)
        seen = await rt.guard.observe(page, navigator=rt.navigator, step=n, tier=1)
        attrs = None
        if op in ("fill", "select") and step.get("selector"):
            attrs = await loc.evaluate("e => ({name: e.getAttribute('name') || '', id: e.id || '', type: e.getAttribute('type') || '',"
                                       " autocomplete: e.getAttribute('autocomplete') || '', aria_label: e.getAttribute('aria-label') || '',"
                                       " label: (e.labels && e.labels[0] ? e.labels[0].innerText : '')})")
        dec = rt.guard.authorise(typed_action(rt, step, label, url), seen, label=label, role=role, url=page.url,
                                 field_attrs=attrs)
        rt.guard.require(dec, label or sid, navigator=rt.navigator)
    try:
        await _execute(rt, step, sid, res, timeout_ms, url, loc)
    except BaseException:
        if rt.guard and dec is not None:
            rt.guard.record(dec, False)
        raise
    if rt.guard and dec is not None:
        rt.guard.record(dec, True)


async def _execute(rt: DslRuntime, step: dict[str, Any], sid: str, res: DslResult, timeout_ms: int,
                   url: str | None, loc: Any) -> None:
    page, op = rt.page, step["op"]
    if op == "goto":
        await page.goto(url, wait_until="domcontentloaded", timeout=max(timeout_ms, 8000))
    elif op == "click":
        await loc.click(timeout=max(timeout_ms, 4000))
    elif op == "fill":
        await loc.fill(resolve_value(step["value"], rt.params), timeout=max(timeout_ms, 4000))
    elif op == "select":
        await loc.select_option(resolve_value(step["value"], rt.params), timeout=max(timeout_ms, 4000))
    elif op == "wait_for":
        wait_ms = int(step.get("timeout_ms", rt.post_timeout_ms))
        try:
            if loc is not None:
                await loc.first.wait_for(state="visible", timeout=wait_ms)
            elif step.get("text") is not None:
                await page.get_by_text(resolve_value(step["text"], rt.params), exact=False).first.wait_for(
                    state="visible", timeout=wait_ms)
            else:
                await page.wait_for_url(lambda u, want=step["url_contains"]: want in u, timeout=wait_ms)
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, f"wait_for {step.get('selector') or step.get('text') or step.get('url_contains')}") from None
    elif op == "assert_text":
        want = resolve_value(step["contains"], rt.params)
        try:
            got = await (loc.first if loc is not None else page.locator("body")).inner_text(timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, "assert_text target missing") from None
        if want.lower() not in got.lower():
            raise PostconditionFailed(sid, f"assert_text {step.get('selector') or 'page'}")
    elif op == "extract":
        try:
            got = (await loc.first.inner_text(timeout=timeout_ms)).strip()
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, f"extract {step['selector']}") from None
        if step.get("pattern"):
            m = re.search(step["pattern"], got)
            got = (m.group(1) if m and m.groups() else m.group(0)) if m else ""
        if step.get("as") == "number":
            m = re.search(r"-?\d[\d,]*\.?\d*", got)
            got = m.group(0).replace(",", "") if m else ""
        res.outputs[step["name"]] = got
