// Small DOM helpers: ARIA role, accessible name, visibility, interactive ancestor. Names are only ever
// hashed (L0) or used for role+name selectors in an opted-in L1 recording.

const INPUT_ROLE: Record<string, string> = {
  button: "button", submit: "button", reset: "button", image: "button", checkbox: "checkbox", radio: "radio",
  range: "slider", number: "spinbutton", search: "searchbox", email: "textbox", tel: "textbox", text: "textbox",
  url: "textbox", password: "textbox", date: "textbox", "datetime-local": "textbox", month: "textbox",
  time: "textbox", week: "textbox",
};

const TAG_ROLE: Record<string, string> = {
  a: "link", button: "button", select: "combobox", textarea: "textbox", img: "img", summary: "button",
  h1: "heading", h2: "heading", h3: "heading", h4: "heading", h5: "heading", h6: "heading",
  p: "paragraph", li: "listitem", td: "cell", th: "cell", tr: "row", table: "table", nav: "navigation",
  form: "form", main: "main", dialog: "dialog", option: "option", article: "article", pre: "text", label: "text",
};

const ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/;

export function roleOf(el: Element): string {
  const explicit = (el.getAttribute("role") ?? "").trim().toLowerCase().split(/\s+/)[0] ?? "";
  if (explicit && ROLE_RE.test(explicit)) return explicit;
  const tag = el.tagName.toLowerCase();
  if (tag === "input") {
    const type = ((el as HTMLInputElement).type || el.getAttribute("type") || "text").toLowerCase();
    return INPUT_ROLE[type] ?? "textbox";
  }
  if (tag === "a" && !el.hasAttribute("href")) return "generic";
  if (tag === "select" && ((el as HTMLSelectElement).multiple || (el as HTMLSelectElement).size > 1)) return "listbox";
  const r = TAG_ROLE[tag];
  if (r) return r;
  if ((el as HTMLElement).isContentEditable) return "textbox";
  return "generic";
}

export const INTERACTIVE_SELECTOR =
  'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [role="menuitem"], ' +
  '[role="checkbox"], [role="radio"], [role="textbox"], [role="searchbox"], [role="combobox"], [role="switch"], [role="option"], [tabindex]';

export function interactiveAncestor(el: Element): Element | null {
  return el.closest(INTERACTIVE_SELECTOR);
}

export function isFormField(el: Element): boolean {
  const tag = el.tagName.toLowerCase();
  if (tag === "input") {
    const type = ((el as HTMLInputElement).type || "text").toLowerCase();
    return !["button", "submit", "reset", "image", "hidden"].includes(type);
  }
  if (tag === "textarea" || tag === "select") return true;
  if ((el as HTMLElement).isContentEditable) return true;
  return ["textbox", "searchbox", "combobox"].includes((el.getAttribute("role") ?? "").toLowerCase());
}

function squash(s: string | null | undefined, max = 80): string {
  return (s ?? "").replace(/\s+/g, " ").trim().slice(0, max);
}

export function accessibleName(el: Element): string {
  const doc = el.ownerDocument;
  const by = el.getAttribute("aria-labelledby");
  if (by) {
    const text = by.split(/\s+/).map((id) => doc.getElementById(id)?.textContent ?? "").join(" ");
    if (squash(text)) return squash(text);
  }
  const aria = squash(el.getAttribute("aria-label"));
  if (aria) return aria;
  const tag = el.tagName.toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") {
    const labels = (el as HTMLInputElement).labels;
    if (labels && labels.length) {
      const t = squash(Array.from(labels).map((l) => l.textContent ?? "").join(" "));
      if (t) return t;
    }
    const type = ((el as HTMLInputElement).type || "").toLowerCase();
    if (["button", "submit", "reset"].includes(type)) return squash((el as HTMLInputElement).value);
    if (type === "image") return squash(el.getAttribute("alt"));
    return squash(el.getAttribute("placeholder")) || squash(el.getAttribute("title")) || squash(el.getAttribute("name"));
  }
  if (tag === "img") return squash(el.getAttribute("alt")) || squash(el.getAttribute("title"));
  const text = squash(el.textContent);
  if (text) return text;
  return squash(el.getAttribute("title"));
}

export function isVisible(el: Element): boolean {
  const he = el as HTMLElement;
  if (he.hidden) return false;
  const win = el.ownerDocument.defaultView;
  if (win) {
    const cs = win.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return false;
  }
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}
