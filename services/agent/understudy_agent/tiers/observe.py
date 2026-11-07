"""Observe a page: interactive elements, visible text, and the text a human would not see.

Hidden text, comments, alt text and aria-labels are collected on purpose: they go to the injection
detector, never to the planner.
"""
from __future__ import annotations

import time
from typing import Any

from ..security.sanitize import sanitize_untrusted
from .base import Element, Observation

_JS = r"""
() => {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[hidden]');
  };
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    if (el.labels && el.labels.length) return el.labels[0].innerText;
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return l.innerText; }
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' && ['submit','button'].includes(el.type)) return el.value;
    return el.innerText || el.getAttribute('title') || el.getAttribute('placeholder') || '';
  };
  document.querySelectorAll('[data-uref]').forEach(e => e.removeAttribute('data-uref'));
  const sel = 'a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link]';
  const els = [];
  let i = 0;
  for (const el of document.querySelectorAll(sel)) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    let role = el.getAttribute('role') || '';
    if (!role) role = tag === 'a' ? 'link' : tag === 'button' ? 'button' : tag === 'select' ? 'combobox'
      : tag === 'textarea' ? 'textbox' : (type === 'submit' || type === 'button') ? 'button'
      : type === 'checkbox' ? 'checkbox' : type === 'radio' ? 'radio' : type === 'number' ? 'spinbutton' : 'textbox';
    const ref = 'e' + (++i);
    el.setAttribute('data-uref', ref);
    els.push({ref, tag, role, type, name: nameOf(el), visible: isVisible(el), enabled: !el.disabled,
      filled: tag === 'select' ? false : (el.value || '').length > 0,
      options: tag === 'select' ? Array.from(el.options).map(o => o.value) : [],
      id: el.id || '', field_name: el.getAttribute('name') || '', testid: el.getAttribute('data-testid') || ''});
  }
  const hidden = [];
  const alts = [];
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_COMMENT);
  while (walker.nextNode()) hidden.push(walker.currentNode.nodeValue);
  for (const el of document.body.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    if (['script','style','noscript','option','select'].includes(tag)) continue;
    for (const a of ['alt','aria-label','title']) { const v = el.getAttribute(a); if (v && v.length > 12) alts.push(v); }
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.nodeValue.trim()).join(' ').trim();
    if (!own || own.length < 12) continue;
    const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    const offscreen = r.right < 0 || r.bottom < 0 || r.left < -500 || r.top < -500;
    const tiny = parseFloat(s.fontSize) <= 3;
    const camo = s.color === s.backgroundColor && s.color !== 'rgba(0, 0, 0, 0)';
    if (!isVisible(el) || offscreen || tiny || camo) hidden.push(own);
  }
  return {url: location.href, title: document.title, text: document.body.innerText || '', elements: els, hidden, alts};
}
"""


def _clean(s: str, n: int) -> str:
    return " ".join(sanitize_untrusted(s or "", max_chars=n).text.split())


async def observe(page: Any, *, max_text: int = 20000) -> Observation:
    raw = await page.evaluate(_JS)
    elements = [
        Element(
            ref=e["ref"], tag=e["tag"], role=e["role"], name=_clean(e["name"], 90), type=e["type"],
            visible=bool(e["visible"]), enabled=bool(e["enabled"]), filled=bool(e["filled"]),
            options=tuple(e["options"]), id=e["id"], field_name=e["field_name"], testid=e["testid"],
        )
        for e in raw["elements"]
    ]
    return Observation(
        url=raw["url"], title=raw["title"], text=(raw["text"] or "")[:max_text], elements=elements,
        hidden_texts=[h for h in raw["hidden"] if h][:40], alt_texts=[a for a in raw["alts"] if a][:40],
        taken_at=time.monotonic(),
    )
