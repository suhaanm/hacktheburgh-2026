"""Run a scripted PROGRAM (a list of step tuples) against a role sandbox page with Playwright (sync API). Used by the sandbox tests, the
expert recordings and the fake participants' unit tests. The step vocabulary is the one the study harness's scripted participant
speaks (the harness resolves a needle against the visible controls of its own snapshot with the same rule):

    ("click", needle)                 click the first visible control whose label contains ``needle`` (case-insensitive)
    ("fill", needle, text)            replace the whole value of a text field / editor
    ("replace", needle, find, repl)   in a text field / editor: replace the first occurrence of ``find`` with ``repl`` (no-op error if absent)
    ("select", needle, option)        choose the dropdown option whose text or value equals / starts with / contains ``option``
    ("wait", seconds)

A control's LABEL is, in this order: aria-label; the text of the first <label> for it; for button, a and summary the inner text;
else placeholder, name or id. Controls are a[href], button, input (not hidden), select, textarea, summary, [role=button], [role=tab],
visible only, in document order. Zero-pad: a needle that matches nothing raises ``ControlNotFound`` (a script bug, not a participant
behaviour).
"""
from __future__ import annotations

import time

CONTROLS_JS = r"""
(needle) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('[hidden]'); };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]';
  const label = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria) return clean(aria);
    if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
    const tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'a' || tag === 'summary') return clean(el.innerText);
    return clean(el.placeholder || el.getAttribute('name') || el.id || '');
  };
  const els = Array.from(document.querySelectorAll(sel)).filter(vis);
  const n = needle.toLowerCase();
  const hit = els.find((el) => label(el).toLowerCase().includes(n));
  window.__progTarget = hit || null;
  return hit ? label(hit) : null;
}
"""


class ControlNotFound(RuntimeError):
    pass


def _target(page, needle: str):
    found = page.evaluate(CONTROLS_JS, needle)
    if found is None:
        raise ControlNotFound(f"no visible control labelled like {needle!r}")
    return page.evaluate_handle("() => window.__progTarget").as_element()


def labels(page) -> list[str]:
    """Every visible control's label, in order (for tests that want to see what a participant sees)."""
    return page.evaluate(r"""() => { const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('[hidden]'); };
      const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
      const label = (el) => { const aria = el.getAttribute('aria-label'); if (aria) return clean(aria);
        if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
        const tag = el.tagName.toLowerCase(); if (tag === 'button' || tag === 'a' || tag === 'summary') return clean(el.innerText);
        return clean(el.placeholder || el.getAttribute('name') || el.id || ''); };
      return Array.from(document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]')).filter(vis).map(label); }""")


def run_step(page, step: tuple, pace: float = 0.0) -> None:
    kind = step[0]
    if kind == "wait":
        time.sleep(float(step[1]))
        return
    el = _target(page, step[1])
    if kind == "click":
        el.click(timeout=6000)
    elif kind == "fill":
        el.fill(step[2], timeout=6000)
    elif kind == "replace":
        cur = el.input_value()
        if step[2] not in cur:
            raise ControlNotFound(f"text {step[2]!r} not found in {step[1]!r}")
        el.fill(cur.replace(step[2], step[3], 1), timeout=6000)
    elif kind == "select":
        want = step[2].strip().lower()
        val = el.evaluate(
            "(e, w) => { const o = Array.from(e.options); const n = s => s.trim().toLowerCase();"
            " const m = o.find(x => n(x.text) === w || n(x.value) === w) || o.find(x => n(x.text).startsWith(w) || n(x.value).startsWith(w))"
            " || o.find(x => n(x.text).includes(w)); return m ? m.value : null; }", want)
        if val is None:
            raise ControlNotFound(f"no option like {step[2]!r} in {step[1]!r}")
        el.select_option(value=val, timeout=4000)
    else:
        raise ValueError(f"unknown step kind {kind!r}")
    if pace:
        time.sleep(pace)


def run_program(page, program: list[tuple], pace: float = 0.0) -> None:
    for step in program:
        run_step(page, step, pace)
