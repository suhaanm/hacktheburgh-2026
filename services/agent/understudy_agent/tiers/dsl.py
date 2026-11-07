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
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .base import Emit, GateStop, PostconditionFailed, PreconditionFailed, StepBudgetExceeded, StepEvent
from .safety import Guard

OPS = {"goto", "click", "fill", "select", "wait_for", "assert_text", "extract", "checkpoint"}
CONDITION_KEYS = {"visible", "exists", "absent", "text_contains", "url_contains", "value_equals"}
MAX_STEPS = 60
STEP_KEYS = {"id", "op", "url", "selector", "role", "name", "value", "contains", "timeout_ms", "pre", "post",
             "optional", "note"}


# ----------------------------------------------------------------------------- validation
def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    """Static checks only (structure, ops, params). The selector and dry-run checks live in compile.py."""
    errs: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle must be an object"]
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
        if op == "goto" and not str(s.get("url", "")).startswith("{base}"):
            errs.append(f"{where}: goto url must start with {{base}}")
        if op in ("click", "fill", "select", "wait_for", "assert_text", "extract"):
            if not (s.get("selector") or (op == "click" and s.get("role") and s.get("name"))):
                errs.append(f"{where}: needs a selector" + (" or role+name" if op == "click" else ""))
        if op in ("fill", "select"):
            errs += _check_value(s.get("value"), declared, where)
        if op == "assert_text":
            errs += _check_value(s.get("contains"), declared, where)
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
                    if k in ("text_contains", "value_equals"):
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
            return f"{key} {v if isinstance(v, str) else v.get('selector', '')}"
    return None


async def run_bundle(bundle: dict[str, Any], rt: DslRuntime) -> DslResult:
    errs = validate_bundle(bundle)
    if errs:
        raise ValueError("invalid bundle: " + "; ".join(errs[:3]))
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
    target = {"selector": step["selector"]} if step.get("selector") else {"role": step["role"], "name": step["name"]}
    if op == "click":
        return {"kind": "click_element", "args": {**target, **({"label": label[:120]} if label else {})}}
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
        url = step["url"].replace("{base}", rt.base_url.rstrip("/"))
        if rt.query and "?" not in url:
            url += rt.query
    loc = None if op == "goto" else _locator(page, step)
    label, role = None, None
    if op in ("click", "fill", "select"):
        try:
            await loc.first.wait_for(state="visible", timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            raise PreconditionFailed(sid, f"target not visible: {step.get('selector') or step.get('name')}") from None
        if await loc.count() != 1:
            raise PreconditionFailed(sid, f"target is not unique ({await loc.count()} matches)")
        label, role = await _label_of(loc)
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
        try:
            await loc.first.wait_for(state="visible", timeout=int(step.get("timeout_ms", rt.post_timeout_ms)))
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, f"wait_for {step['selector']}") from None
    elif op == "assert_text":
        want = resolve_value(step["contains"], rt.params)
        try:
            got = await loc.first.inner_text(timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, f"assert_text target missing {step['selector']}") from None
        if want.lower() not in got.lower():
            raise PostconditionFailed(sid, f"assert_text {step['selector']}")
    elif op == "extract":
        try:
            res.outputs[step["name"]] = (await loc.first.inner_text(timeout=timeout_ms)).strip()
        except Exception:  # noqa: BLE001
            raise PostconditionFailed(sid, f"extract {step['selector']}") from None
