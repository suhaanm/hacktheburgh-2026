// meta.zone: a short enum token naming the page region an event happened in (CAP-4: no page text).
// Source of the config: each pack's tasks/sites.yaml `capture:` or mapping.yaml `capture_sites`, bundled
// by scripts/gen.mjs. Only the presence of elements is tested, never their text.
// Fallbacks without a site config: generic base zones from the ARIA role (form_field, search_box).
// An element or ancestor may also say so itself with data-understudy-zone="<zone>" (vocabulary values only).

export interface ZoneWhen { zone: string; when: string }
export interface ZoneSite {
  pack: string;
  id: string;
  hosts: string[];
  nav_default: string;
  tab_default: string;
  nav?: ZoneWhen[];
  tab?: ZoneWhen[];
  page?: ZoneWhen[];
  elements: { zone: string; selector: string }[];
}
export interface ZoneConfig { vocabulary: string[]; sites: ZoneSite[] }

function hostMatches(pattern: string, host: string): boolean {
  if (pattern === host) return true;
  if (pattern.startsWith("*.")) return host.endsWith(pattern.slice(1)) && host.length > pattern.length - 1;
  return false;
}

/** The first site config whose hosts match location.host (hostname[:port], lower case). */
export function pickSite(cfg: ZoneConfig, host: string, packs?: string[]): ZoneSite | null {
  const h = host.toLowerCase();
  for (const s of cfg.sites) {
    if (packs && packs.length && !packs.includes(s.pack)) continue;
    if (s.hosts.some((p) => hostMatches(p, h))) return s;
  }
  return null;
}

function safeQuery(root: ParentNode, selector: string): boolean {
  try {
    return root.querySelector(selector) !== null;
  } catch {
    return false;
  }
}

function firstWhen(doc: Document, rules: ZoneWhen[] | undefined): string | null {
  for (const r of rules ?? []) if (safeQuery(doc, r.when)) return r.zone;
  return null;
}

export class Zoner {
  private readonly vocab: Set<string>;
  constructor(private readonly cfg: ZoneConfig, private readonly site: ZoneSite | null) {
    this.vocab = new Set(cfg.vocabulary);
  }

  /** Zone for an element event (click, focus, copy, paste, element scroll). */
  forElement(el: Element, role: string): string | undefined {
    const marked = el.closest("[data-understudy-zone]")?.getAttribute("data-understudy-zone") ?? "";
    if (marked && this.vocab.has(marked)) return marked;
    if (this.site) {
      for (const rule of this.site.elements) {
        try {
          if (el.closest(rule.selector)) return rule.zone;
        } catch {
          // a bad selector in a pack must not break capture
        }
      }
    }
    return this.generic(role);
  }

  /** Document-level scroll: the page's dominant zone. */
  forScroll(doc: Document): string | undefined {
    if (this.site) {
      const z = firstWhen(doc, this.site.page);
      if (z) return z;
    }
    return "doc";
  }

  forNav(doc: Document): string | undefined {
    if (!this.site) return undefined;
    return firstWhen(doc, this.site.nav) ?? this.site.nav_default;
  }

  forTab(doc: Document): string | undefined {
    if (!this.site) return undefined;
    return firstWhen(doc, this.site.tab) ?? this.site.tab_default;
  }

  private generic(role: string): string | undefined {
    if (role === "searchbox") return "search_box";
    if (["textbox", "combobox", "spinbutton", "checkbox", "radio", "slider"].includes(role)) return "form_field";
    return undefined;
  }
}
