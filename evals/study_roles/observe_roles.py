"""What a participant sees in a role sandbox and the typed actions it can take. Same idea as ``evals/study_sim/observe.py`` (the page as a person sees it: text,
a numbered list of visible controls with labels and values; no attributes, zones or ids are shown), with the differences this study needs:

* the page text is longer and the full text of any text box (the code editor) is included, because a person reads the code they are editing;
* an extra action ``replace`` (find a piece of text in a text box and replace it) next to ``fill`` (replace everything), the way a person edits;
* no value cleaning: the forms of the sandboxes are forgiving (a bad value gives a visible, correctable error on the same page), so nothing is repaired for the participant.

The control list and its labels follow exactly the rule of ``understudy_agent.sandbox_roles.programs_util`` so scripted programs and models see the same controls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from evals.study_sim.observe import HIDE_OVERLAY_JS, OVERLAY_JS, Executed, render_elements, url_allowed, url_parts   # noqa: F401  (re-exported)

KINDS = ("click", "fill", "select", "replace", "goto", "wait", "dismiss_coach", "finish")
MAX_TEXT = 6000
MAX_FIELD = 3200

SNAPSHOT_JS = r"""
(snapId) => {
  const vis = (el) => {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && !el.closest('[hidden]');
  };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab]';
  const els = Array.from(document.querySelectorAll(sel)).filter(vis);
  const label = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria) return clean(aria);
    if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
    const tag = el.tagName.toLowerCase();
    if (tag === 'button' || tag === 'a' || tag === 'summary') return clean(el.innerText);
    return clean(el.placeholder || el.getAttribute('name') || el.id || '');
  };
  window.__simRefs = els; window.__simSnap = snapId;
  const ring = window.__simRingTarget || null;
  const out = els.map((el, i) => {
    const tag = el.tagName.toLowerCase();
    const z = el.closest('[data-understudy-zone]');
    const o = { ref: i, tag, label: label(el).slice(0, 90), dom_id: el.id || '', zone: z ? z.getAttribute('data-understudy-zone') : '' };
    if (tag === 'input' || tag === 'textarea') { o.type = el.type || 'text'; o.value = (el.value || '').slice(0, tag === 'textarea' ? 20 : 80); }
    if (tag === 'input' && (el.type === 'checkbox' || el.type === 'radio')) o.value = el.checked ? 'checked' : 'unchecked';
    if (tag === 'select') {
      o.options = Array.from(el.options).map(op => ({ value: op.value, text: clean(op.text).slice(0, 60) }));
      o.value = el.value;
    }
    if (el.disabled) o.disabled = true;
    if (ring && el === ring) o.ringed = true;
    return o;
  });
  const fields = els.filter(e => e.tagName.toLowerCase() === 'textarea').map(e => ({ label: label(e), text: (e.value || '').slice(0, %MAX_FIELD%) }));
  const main = document.querySelector('main') || document.body;
  const text = (main.innerText || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  return { url: location.href, title: document.title, text, elements: out, fields, ring_in_page: !!ring };
}
""".replace("%MAX_FIELD%", str(MAX_FIELD))


@dataclass
class RAction:
    kind: str
    ref: int | None = None
    text: str | None = None
    find: str | None = None
    url: str | None = None
    seconds: float | None = None

    def brief(self) -> str:
        return " ".join(str(x) for x in (self.kind, f"ref={self.ref}" if self.ref is not None else "", self.url or "") if x)


def parse_actions(obj: dict, max_actions: int = 4) -> list[RAction]:
    """Validate the model's JSON into actions. Unknown kinds are dropped; the first ``max_actions`` valid ones are kept."""
    out: list[RAction] = []
    for a in (obj.get("actions") or []):
        if len(out) >= max_actions:
            break
        if not isinstance(a, dict):
            continue
        kind = str(a.get("kind", "")).strip().lower()
        if kind not in KINDS:
            continue
        ref = a.get("ref")
        ref = int(ref) if isinstance(ref, (int, float)) and not isinstance(ref, bool) else None
        secs = a.get("seconds")
        text, find = a.get("text"), a.get("find")
        out.append(RAction(kind=kind, ref=ref, text=None if text is None else str(text)[:6000], find=None if find is None else str(find)[:2000],
                           url=(str(a["url"]) if a.get("url") else None), seconds=float(secs) if isinstance(secs, (int, float)) and not isinstance(secs, bool) else None))
    return out


def snapshot_text(snap: dict) -> str:
    parts = [snap.get("text", "")[:MAX_TEXT]]
    for f in snap.get("fields", []):
        parts.append(f"\nText box \"{f['label']}\" (full content):\n{f['text']}")
    return "\n".join(parts)


def is_forbidden(label: str, dom_id: str, forbidden_id: str, forbidden_label: str) -> bool:
    return dom_id == forbidden_id or forbidden_label.lower() in (label or "").lower()


def match_option_js() -> str:
    return ("(e, w) => { const o = Array.from(e.options); const n = s => s.trim().toLowerCase(); w = n(w);"
            " const m = o.find(x => n(x.text) === w || n(x.value) === w) || o.find(x => n(x.text).startsWith(w) || n(x.value).startsWith(w))"
            " || o.find(x => n(x.text).includes(w)); return m ? m.value : null; }")
