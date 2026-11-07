"""What the participant sees, and the typed actions it can take.

The snapshot is built in the page by a small script (visible text plus a numbered list of the visible controls with their
labels and current values), the way a person sees a page: no attributes, no zones, no ids are shown. Actions are typed
(click, fill, select, goto, wait, new_tab, switch_tab, dismiss_coach, finish) and run through Playwright, so they arrive in
the page as trusted events and the real extension captures them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("click", "fill", "select", "goto", "wait", "new_tab", "switch_tab", "dismiss_coach", "finish")
SUBMIT_RE = re.compile(r"submit\s+to\s+claimant", re.I)
SUBMIT_IDS = {"submit-note", "cn-submit"}
MAX_TEXT = 1400

# Runs in the page. Refs are indexes into window.__simRefs; nothing is written into the page's DOM.
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
    const o = { ref: i, tag, label: label(el).slice(0, 90), dom_id: el.id || '' };
    if (tag === 'input' || tag === 'textarea') { o.type = el.type || 'text'; o.value = (el.value || '').slice(0, 60); }
    if (tag === 'select') {
      o.options = Array.from(el.options).map(op => ({ value: op.value, text: clean(op.text).slice(0, 50) }));
      o.value = el.value;
    }
    if (el.disabled) o.disabled = true;
    if (ring && el === ring) o.ringed = true;
    return o;
  });
  const main = document.querySelector('main') || document.body;
  let text = clean(main.innerText);
  return { url: location.href, title: document.title, text, elements: out, ring_in_page: !!ring };
}
"""

# the coach overlay: a ring around the element carrying data-understudy-zone=<zone> plus the message line, inside a shadow root
# (so it is not part of the page text) with pointer-events:none on the ring (clicks pass through). Dismissal is a harness
# call, not a DOM click: the real overlay is a separate desktop window, so it produces no page events.
OVERLAY_JS = r"""
({message, zone, action}) => {
  const old = document.getElementById('__sim_overlay'); if (old) old.remove();
  window.__simRingTarget = null;
  const host = document.createElement('div'); host.id = '__sim_overlay';
  host.style.cssText = 'all:initial;position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
  const root = host.attachShadow({mode: 'open'});
  const bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);max-width:70vw;background:#1b1b1f;color:#fff;font:14px system-ui;padding:8px 14px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.35);';
  bar.textContent = 'Understudy: ' + message;
  root.appendChild(bar);
  let found = false;
  if (zone) {
    const target = Array.from(document.querySelectorAll('[data-understudy-zone="' + zone + '"]')).find(e => {
      const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest('[hidden]'); });
    if (target) {
      found = true; window.__simRingTarget = target;
      const ring = document.createElement('div');
      ring.style.cssText = 'position:fixed;border:3px solid #ff8a00;border-radius:8px;box-shadow:0 0 0 4px rgba(255,138,0,.25);pointer-events:none;';
      root.appendChild(ring);
      const place = () => { if (!ring.isConnected) return; const r = target.getBoundingClientRect();
        ring.style.left = (r.left - 4) + 'px'; ring.style.top = (r.top - 4) + 'px'; ring.style.width = (r.width + 8) + 'px'; ring.style.height = (r.height + 8) + 'px';
        requestAnimationFrame(place); };
      place();
    }
  }
  document.documentElement.appendChild(host);
  return {found};
}
"""
HIDE_OVERLAY_JS = "() => { const o = document.getElementById('__sim_overlay'); if (o) o.remove(); window.__simRingTarget = null; return true; }"


@dataclass
class Action:
    kind: str
    ref: int | None = None
    text: str | None = None
    url: str | None = None
    seconds: float | None = None

    def brief(self) -> str:
        bits = [self.kind]
        if self.ref is not None:
            bits.append(f"ref={self.ref}")
        if self.url:
            bits.append(self.url)
        if self.seconds is not None:
            bits.append(f"{self.seconds:g}s")
        return " ".join(bits)


@dataclass
class Executed:
    """A record of one executed action: kinds and zones/ids only (never page text, never typed text)."""
    t: float
    kind: str
    ok: bool
    t_wall: float = 0.0
    dom_id: str = ""
    label: str = ""              # kept in memory for the follow rule and the history shown to the participant; not written to actions.jsonl
    port: int | None = None
    site: str | None = None
    path: str = ""
    error: str = ""
    page_changed: bool = False
    violation: str = ""
    extra: dict = field(default_factory=dict)


def parse_actions(obj: dict, max_actions: int = 4) -> list[Action]:
    """Validate the model's JSON into Actions. Unknown kinds are dropped; the first ``max_actions`` valid ones are kept."""
    out: list[Action] = []
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
        text = a.get("text")
        secs = a.get("seconds")
        out.append(Action(kind=kind, ref=ref, text=None if text is None else str(text)[:200], url=(str(a["url"]) if a.get("url") else None),
                          seconds=float(secs) if isinstance(secs, (int, float)) and not isinstance(secs, bool) else None))
    return out


_JSON_CUT = re.compile(r'[}{\[\]"\\]')


def clean_typed(text: str) -> str:
    """Remove artifacts of the structured reply from a value the participant 'types', the same for every participant in every arm.
    (1) Everything from the first JSON structure character on ('36},{' -> '36'). (2) Trailing ',' or ';'. (3) A trailing run of '?' or '/' after a digit
    ('12000/' -> '12000'). (4) A single token repeated four or more times ('42 42 42 42' -> '42'). Currency symbols, words, wrong numbers and every
    other human-like mistake are left alone."""
    t = text or ""
    m = _JSON_CUT.search(t)
    if m:
        t = t[:m.start()]
    t = t.strip().rstrip(",;").rstrip()
    t = re.sub(r"(?<=\d)[?/]+$", "", t).rstrip()
    toks = t.split()
    if len(toks) >= 4 and len(set(toks)) == 1:
        t = toks[0]
    return t


def url_allowed(url: str, ports: set[int]) -> bool:
    m = re.match(r"^http://127\.0\.0\.1:(\d+)(/.*)?$", url or "")
    return bool(m and int(m.group(1)) in ports)


def is_submit_control(label: str, dom_id: str) -> bool:
    return bool(SUBMIT_RE.search(label or "")) or dom_id in SUBMIT_IDS


def url_parts(url: str) -> tuple[int | None, str]:
    m = re.match(r"^https?://[^:/]+:(\d+)(/[^?#]*)?", url or "")
    return (int(m.group(1)), m.group(2) or "/") if m else (None, "")


def render_elements(elements: list[dict]) -> str:
    lines = []
    for e in elements:
        desc = {"button": "button", "a": "link", "summary": "button", "select": "dropdown", "textarea": "text box",
                "input": {"checkbox": "checkbox", "radio": "radio"}.get(e.get("type", ""), "text field")}.get(e["tag"], e["tag"])
        s = f"({e['ref']}) {desc} \"{e['label']}\""
        if e["tag"] == "select":
            opts = ", ".join(o["text"] or o["value"] for o in e.get("options", []))
            cur = next((o["text"] or o["value"] for o in e.get("options", []) if o["value"] == e.get("value")), "")
            s += f" options: {opts}; currently: {cur}"
        elif e["tag"] in ("input", "textarea"):
            s += f" value: \"{e.get('value', '')}\""
        if e.get("disabled"):
            s += " (disabled)"
        if e.get("ringed"):
            s += "  -- ringed in orange by the helper app"
        lines.append(s)
    return "\n".join(lines)
