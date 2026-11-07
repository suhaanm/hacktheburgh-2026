// Sensitive-field matcher (CAP-4). The list is data (packages/schema/sensitive_fields.json plus each pack's
// additions, bundled at build time). Anything this matcher flags is never recorded, never hashed, never
// measured: no event, no L1 step, no rect. The check looks at field name, id, label, placeholder,
// autocomplete, aria-label and similar attributes, at the input type, and at the surrounding form.

export interface SensitiveSpec {
  patterns: string[];
  autocomplete_tokens?: string[];
  input_types?: string[];
}

const ATTRS = ["name", "id", "placeholder", "aria-label", "autocomplete", "title", "data-testid", "data-test", "data-cy", "inputmode"];

export class SensitiveMatcher {
  private readonly patterns: RegExp[] = [];
  private readonly tokens = new Set<string>();
  private readonly types = new Set<string>();

  constructor(specs: SensitiveSpec[]) {
    for (const spec of specs) {
      for (const p of spec.patterns) {
        try {
          this.patterns.push(new RegExp(p, "i"));
        } catch {
          // A pattern that does not compile must not silently weaken the list: fail closed on its literal text.
          this.patterns.push(new RegExp(p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"));
        }
      }
      for (const t of spec.autocomplete_tokens ?? []) this.tokens.add(t.toLowerCase());
      for (const t of spec.input_types ?? []) this.types.add(t.toLowerCase());
    }
  }

  /**
   * Field names are often snake_case, dotted or camelCase (ni_number, nationalInsurance), which the list's
   * word-boundary patterns do not see. Test the raw text and two spaced-out variants.
   */
  isSensitiveText(s: string | null | undefined): boolean {
    if (!s) return false;
    const spaced = s.replace(/[_.\-]+/g, " ");
    const camel = s.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_.]+/g, " ");
    return this.patterns.some((re) => re.test(s) || re.test(spaced) || re.test(camel));
  }

  /** The element itself: type, autocomplete tokens, and every identifying attribute and label. */
  isSensitiveElement(el: Element): boolean {
    const tag = el.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") {
      const type = ((el as HTMLInputElement).type || el.getAttribute("type") || "text").toLowerCase();
      if (this.types.has(type)) return true;
    }
    const auto = (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/);
    if (auto.some((t) => this.tokens.has(t))) return true;
    for (const a of ATTRS) if (this.isSensitiveText(el.getAttribute(a))) return true;
    for (const text of this.labelTexts(el)) if (this.isSensitiveText(text)) return true;
    return false;
  }

  /** The element, or a form (or nearby container) that holds a password or other sensitive control. */
  inSensitiveContext(el: Element): boolean {
    if (this.isSensitiveElement(el)) return true;
    const form = el.closest("form");
    if (form) return this.containerHasSensitiveControl(form);
    // No form: look a few ancestors up for a login-style container (single page apps).
    let node: Element | null = el.parentElement;
    for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
      if (node.tagName === "BODY" || node.tagName === "HTML") break;
      if (this.containerHasSensitiveControl(node)) return true;
    }
    return false;
  }

  private containerHasSensitiveControl(root: Element): boolean {
    const controls = root.querySelectorAll("input, textarea, select");
    for (const c of Array.from(controls)) {
      const type = ((c as HTMLInputElement).type || c.getAttribute("type") || "text").toLowerCase();
      if (type === "hidden" || type === "submit" || type === "button") continue;
      // Input types such as email or tel are only sensitive as a field, not as a reason to drop a whole form.
      if (type === "password" || this.tokensIn(c) || this.patternsIn(c)) return true;
    }
    return false;
  }

  private tokensIn(c: Element): boolean {
    const auto = (c.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/);
    return auto.some((t) => this.tokens.has(t));
  }

  private patternsIn(c: Element): boolean {
    for (const a of ["name", "id", "autocomplete", "aria-label", "placeholder"]) {
      if (this.isSensitiveText(c.getAttribute(a))) return true;
    }
    return false;
  }

  private labelTexts(el: Element): string[] {
    const out: string[] = [];
    const doc = el.ownerDocument;
    const labels = (el as HTMLInputElement).labels;
    if (labels) for (const l of Array.from(labels)) out.push(l.textContent ?? "");
    const wrap = el.closest("label");
    if (wrap) out.push(wrap.textContent ?? "");
    const by = el.getAttribute("aria-labelledby");
    if (by) for (const id of by.split(/\s+/)) out.push(doc.getElementById(id)?.textContent ?? "");
    return out;
  }
}
