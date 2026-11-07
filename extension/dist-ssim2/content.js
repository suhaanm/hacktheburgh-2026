"use strict";
(() => {
  // generated-config:bundled.json
  var bundled_default = { sensitive: [{ description: "Fields that are NEVER recorded or read (CAP-4, SEC). Data, not code: extend freely. Matched case-insensitively as regex against field name, id, label, placeholder, autocomplete and aria-label.", patterns: ["pass(word|wd|code|phrase)?", "\\bpin\\b", "\\botp\\b", "one[- ]?time", "2fa|mfa|verification[- ]code|security[- ]code", "\\bcvv\\b|\\bcvc\\b|card[- ]?(number|no)|credit|debit", "\\biban\\b|sort[- ]?code|account[- ]?(number|no)|routing", "national[- ]?insurance|\\bni[- ]?(number|no)\\b|\\bnino\\b|\\bssn\\b|social[- ]security", "passport|driving[- ]?licen[cs]e|date[- ]of[- ]birth|\\bdob\\b", "secret|token|api[- ]?key|private[- ]key|seed[- ]phrase", "cc-number|cc-csc|cc-exp|current-password|new-password|one-time-code"], autocomplete_tokens: ["cc-number", "cc-csc", "cc-exp", "current-password", "new-password", "one-time-code"], input_types: ["password"] }, { description: "Benefits-processor additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Data, not code: extend freely. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["\\bnino\\b|national[- ]?insurance|\\bni[- ]?(no|number)\\b", "claimant[- ]?(name|surname|forename|address|phone|email)", "(partner|spouse|child|children|dependant)[- ]?(name|dob|date[- ]of[- ]birth)", "(home|postal|street)[- ]?address|\\bpostcode\\b|\\bpost[- ]?code\\b|\\bzip\\b", "\\bphone\\b|\\bmobile\\b|\\bemail\\b", "\\butr\\b|unique[- ]?taxpayer|tax[- ]?(code|reference)", "bank[- ]?(name|details)|payee|direct[- ]?debit", "medical|diagnos|health[- ]?condition|disability[- ]?(type|detail)|\\bpip\\b[- ]?(ref|reference)", "immigration|visa|biometric|right[- ]to[- ]rent|residence[- ]permit", "benefit[- ]?claim[- ]?(ref|reference|number)|universal[- ]?credit[- ]?(ref|id)"], autocomplete_tokens: ["street-address", "address-line1", "address-line2", "postal-code", "tel", "email", "bday"], input_types: ["password", "tel", "email"] }, { description: "Data-analyst additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["connection[- ]?string|dsn|jdbc", "warehouse[- ]?(user|password|key)|service[- ]?account|credentials?", "access[- ]?key|secret[- ]?key|bearer", "(customer|user|patient|employee)[- ]?(name|email|phone|address|id)", "\\bemail\\b|\\bphone\\b|\\bmobile\\b|\\bpostcode\\b|\\bpost[- ]?code\\b"], autocomplete_tokens: ["email", "tel", "street-address", "postal-code"], input_types: ["password", "email", "tel"] }, { description: "Programmer additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["personal[- ]?access[- ]?token|\\bpat\\b|deploy[- ]?key|ssh[- ]?key|gpg|signing[- ]?key", "env(ironment)?[- ]?(var|variable)s?[- ]?(value|secret)|\\.env", "client[- ]?secret|webhook[- ]?secret|bearer|authorization", "recovery[- ]?code|backup[- ]?code", "\\bemail\\b"], autocomplete_tokens: ["email"], input_types: ["password", "email"] }], zones: { vocabulary: ["calc_result", "calc_site", "case_note", "chart_panel", "check_box", "ci_log", "cliff_button", "cliff_panel", "code_editor", "code_view", "commit_box", "compare_view", "data_browser", "decision_btn", "diff_view", "doc", "docs_page", "export_panel", "form_field", "help", "household_form", "profile_panel", "query_edit", "query_result", "results_tabs", "run_control", "search_box", "sql_editor", "test_runner"], sites: [{ pack: "benefits-processor", id: "a", hosts: ["127.0.0.1:7931", "localhost:7931"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }, { zone: "calc_result", when: "#result-amount, #calc-total" }, { zone: "household_form", when: 'form input[type="hidden"]' }], tab: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }], page: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }, { zone: "calc_result", when: "#result-amount, #calc-total" }, { zone: "household_form", when: 'form[action^="/step"], form[action^="/result"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: "#result-amount, #calc-total" }, { kind: "note_field", when: "#note-status, #cn-state" }], task_end: { when: "#note-status, #cn-state", reason: "note_saved" } }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "case_note", selector: 'form[action^="/casenote"], #note-id, #note-status, #note-body, #cn-id, #cn-state, #cn-text' }, { zone: "calc_result", selector: "#result-amount, #result-status, #result-ref, #calc-total, #calc-outcome, #calc-reference" }, { zone: "household_form", selector: 'form[action^="/step"], form[action^="/result"]' }] }, { pack: "benefits-processor", id: "b", hosts: ["127.0.0.1:7932", "localhost:7932"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "calc_result", when: "table" }], page: [{ zone: "calc_result", when: "table" }, { zone: "household_form", when: 'form[action^="/calculate"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: "#estimate-monthly, #est-amount" }] }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "calc_result", selector: "table" }, { zone: "household_form", selector: 'form[action^="/calculate"]' }] }, { pack: "benefits-processor", id: "c", hosts: ["127.0.0.1:7933", "localhost:7933"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "calc_result", when: "table" }], page: [{ zone: "calc_result", when: "table" }, { zone: "household_form", when: 'form[action^="/results"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: '[data-testid="out-amount"], [data-testid="x-out-amount"]' }] }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "calc_result", selector: "table" }, { zone: "household_form", selector: 'form[action^="/results"]' }] }, { pack: "data-analyst", id: "warehouse", hosts: ["*.snowflakecomputing.com", "console.cloud.google.com", "*.databricks.com"], nav_default: "data_browser", tab_default: "compare_view", elements: [{ zone: "sql_editor", selector: '.monaco-editor, [role="textbox"][aria-label], .cm-editor' }, { zone: "run_control", selector: 'button[data-testid*="run"], button[aria-label*="Run"]' }, { zone: "query_result", selector: '[role="grid"], [role="table"], .results' }] }, { pack: "data-analyst", id: "notebook", hosts: ["colab.research.google.com", "app.hex.tech", "localhost:8888"], nav_default: "data_browser", tab_default: "compare_view", elements: [{ zone: "sql_editor", selector: ".cm-editor, .monaco-editor, .CodeMirror" }, { zone: "run_control", selector: 'button[aria-label*="Run"], .run-button' }, { zone: "query_result", selector: '.output_area, .jp-OutputArea, [role="table"]' }, { zone: "chart_panel", selector: "canvas, svg.plot, .output_png" }] }, { pack: "data-analyst", id: "sheet", hosts: ["docs.google.com"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "chart_panel", selector: '[aria-label*="Chart"], .chart-container' }] }, { pack: "data-analyst", id: "bi", hosts: ["*.looker.com", "app.powerbi.com", "*.tableau.com"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "chart_panel", selector: 'svg, canvas, [data-testid*="chart"]' }, { zone: "export_panel", selector: 'button[aria-label*="Export"], button[aria-label*="Download"]' }] }, { pack: "programmer", id: "git_host", hosts: ["github.com", "gitlab.com", "bitbucket.org"], nav_default: "code_view", tab_default: "compare_view", elements: [{ zone: "commit_box", selector: '#commit-changes-modal, form[action*="commit"], [data-testid="commit-button"]' }, { zone: "code_editor", selector: '.cm-editor, .monaco-editor, textarea[name="value"]' }, { zone: "diff_view", selector: '#files, .diff-view, [data-testid="diff"]' }, { zone: "code_view", selector: '#read-only-cursor-text-area, .blob-wrapper, [data-testid="code-view"], table.highlight' }] }, { pack: "programmer", id: "ci", hosts: ["*.circleci.com", "buildkite.com", "localhost:8080"], nav_default: "ci_log", tab_default: "compare_view", elements: [{ zone: "test_runner", selector: 'button[aria-label*="Re-run"], button[aria-label*="Rerun"], [data-testid*="rerun"]' }, { zone: "ci_log", selector: 'pre, .log, [data-testid*="log"]' }] }, { pack: "programmer", id: "tracker", hosts: ["*.atlassian.net", "linear.app"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "form_field", selector: 'textarea, input[type="text"]' }] }, { pack: "programmer", id: "docs", hosts: ["docs.python.org", "developer.mozilla.org", "stackoverflow.com", "*.readthedocs.io"], nav_default: "docs_page", tab_default: "docs_page", elements: [{ zone: "docs_page", selector: "main, article, #content, .answercell" }] }] } };

  // src/shared/hash.ts
  var K = new Uint32Array([
    1116352408,
    1899447441,
    3049323471,
    3921009573,
    961987163,
    1508970993,
    2453635748,
    2870763221,
    3624381080,
    310598401,
    607225278,
    1426881987,
    1925078388,
    2162078206,
    2614888103,
    3248222580,
    3835390401,
    4022224774,
    264347078,
    604807628,
    770255983,
    1249150122,
    1555081692,
    1996064986,
    2554220882,
    2821834349,
    2952996808,
    3210313671,
    3336571891,
    3584528711,
    113926993,
    338241895,
    666307205,
    773529912,
    1294757372,
    1396182291,
    1695183700,
    1986661051,
    2177026350,
    2456956037,
    2730485921,
    2820302411,
    3259730800,
    3345764771,
    3516065817,
    3600352804,
    4094571909,
    275423344,
    430227734,
    506948616,
    659060556,
    883997877,
    958139571,
    1322822218,
    1537002063,
    1747873779,
    1955562222,
    2024104815,
    2227730452,
    2361852424,
    2428436474,
    2756734187,
    3204031479,
    3329325298
  ]);
  function utf8(str) {
    const out = [];
    for (let i = 0; i < str.length; i++) {
      let c = str.charCodeAt(i);
      if (c >= 55296 && c <= 56319 && i + 1 < str.length) {
        const d = str.charCodeAt(i + 1);
        if (d >= 56320 && d <= 57343) {
          c = 65536 + (c - 55296 << 10) + (d - 56320);
          i++;
        }
      }
      if (c < 128) out.push(c);
      else if (c < 2048) out.push(192 | c >> 6, 128 | c & 63);
      else if (c < 65536) out.push(224 | c >> 12, 128 | c >> 6 & 63, 128 | c & 63);
      else out.push(240 | c >> 18, 128 | c >> 12 & 63, 128 | c >> 6 & 63, 128 | c & 63);
    }
    return Uint8Array.from(out);
  }
  function sha256Hex(input) {
    const msg = utf8(input);
    const len = msg.length;
    const padded = new Uint8Array(len + 9 + 63 >> 6 << 6);
    padded.set(msg);
    padded[len] = 128;
    const view = new DataView(padded.buffer);
    view.setUint32(padded.length - 8, Math.floor(len * 8 / 4294967296));
    view.setUint32(padded.length - 4, len * 8 >>> 0);
    const h = new Uint32Array([1779033703, 3144134277, 1013904242, 2773480762, 1359893119, 2600822924, 528734635, 1541459225]);
    const w = new Uint32Array(64);
    const rotr = (x, n) => x >>> n | x << 32 - n;
    for (let off = 0; off < padded.length; off += 64) {
      for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4);
      for (let i = 16; i < 64; i++) {
        const w15 = w[i - 15], w2 = w[i - 2];
        const s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ w15 >>> 3;
        const s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ w2 >>> 10;
        w[i] = w[i - 16] + s0 + w[i - 7] + s1 >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i++) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = e & f ^ ~e & g;
        const t1 = hh + S1 + ch + K[i] + w[i] >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = a & b ^ a & c ^ b & c;
        const t2 = S0 + maj >>> 0;
        hh = g;
        g = f;
        f = e;
        e = d + t1 >>> 0;
        d = c;
        c = b;
        b = a;
        a = t1 + t2 >>> 0;
      }
      h[0] = h[0] + a >>> 0;
      h[1] = h[1] + b >>> 0;
      h[2] = h[2] + c >>> 0;
      h[3] = h[3] + d >>> 0;
      h[4] = h[4] + e >>> 0;
      h[5] = h[5] + f >>> 0;
      h[6] = h[6] + g >>> 0;
      h[7] = h[7] + hh >>> 0;
    }
    return Array.from(h, (x) => x.toString(16).padStart(8, "0")).join("");
  }
  function normaliseLabel(s) {
    return s.replace(/\s+/g, " ").trim().toLowerCase().slice(0, 120);
  }
  var HEX_LEN = 12;
  function salted(kind, salt2, value) {
    return sha256Hex(`${kind}\0${salt2}\0${value}`).slice(0, HEX_LEN);
  }
  var hashLabel = (salt2, label) => `h:${salted("label", salt2, normaliseLabel(label))}`;
  var hashDomain = (salt2, host) => `d:${salted("domain", salt2, host.toLowerCase())}`;
  var hashQuery = (salt2, query) => `h:${salted("query", salt2, normaliseLabel(query))}`;

  // src/shared/types.ts
  var DEFAULT_CONFIG = {
    capturing: false,
    // opt-in: nothing is captured until the worker turns it on (PR3)
    person: "",
    role: "benefits-processor",
    engine_url: "http://127.0.0.1:7700",
    desktop_url: "http://127.0.0.1:7720",
    identity_adopted: false
  };
  var STORAGE_KEYS = {
    config: "config",
    salt: "salt",
    queue: "queue",
    task: "task",
    l1Targets: "l1_targets",
    stats: "stats"
  };

  // src/shared/config.ts
  var PERSON_RE = /^p_[a-z0-9]{2,16}$/;
  var ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/;
  function cleanUrl(v, fallback) {
    if (typeof v !== "string") return fallback;
    try {
      const u = new URL(v);
      if (u.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(u.hostname)) return fallback;
      return `${u.protocol}//${u.host}`;
    } catch {
      return fallback;
    }
  }
  function normaliseConfig(raw) {
    const r = typeof raw === "object" && raw !== null ? raw : {};
    return {
      capturing: r.capturing === true,
      person: typeof r.person === "string" && PERSON_RE.test(r.person) ? r.person : "",
      role: typeof r.role === "string" && ROLE_RE.test(r.role) ? r.role : DEFAULT_CONFIG.role,
      engine_url: cleanUrl(r.engine_url, DEFAULT_CONFIG.engine_url),
      desktop_url: cleanUrl(r.desktop_url, DEFAULT_CONFIG.desktop_url),
      identity_adopted: r.identity_adopted === true
    };
  }
  async function loadConfig(area) {
    const got = await area.get(STORAGE_KEYS.config);
    return normaliseConfig(got[STORAGE_KEYS.config]);
  }

  // src/shared/sensitive.ts
  var ATTRS = ["name", "id", "placeholder", "aria-label", "autocomplete", "title", "data-testid", "data-test", "data-cy", "inputmode"];
  var SensitiveMatcher = class {
    patterns = [];
    tokens = /* @__PURE__ */ new Set();
    types = /* @__PURE__ */ new Set();
    constructor(specs) {
      for (const spec of specs) {
        for (const p of spec.patterns) {
          try {
            this.patterns.push(new RegExp(p, "i"));
          } catch {
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
    isSensitiveText(s) {
      if (!s) return false;
      const spaced = s.replace(/[_.\-]+/g, " ");
      const camel = s.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/[_.]+/g, " ");
      return this.patterns.some((re) => re.test(s) || re.test(spaced) || re.test(camel));
    }
    /** The element itself: type, autocomplete tokens, and every identifying attribute and label. */
    isSensitiveElement(el) {
      const tag = el.tagName.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") {
        const type = (el.type || el.getAttribute("type") || "text").toLowerCase();
        if (this.types.has(type)) return true;
      }
      const auto = (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/);
      if (auto.some((t) => this.tokens.has(t))) return true;
      for (const a of ATTRS) if (this.isSensitiveText(el.getAttribute(a))) return true;
      for (const text of this.labelTexts(el)) if (this.isSensitiveText(text)) return true;
      return false;
    }
    /** The element, or a form (or nearby container) that holds a password or other sensitive control. */
    inSensitiveContext(el) {
      if (this.isSensitiveElement(el)) return true;
      const form = el.closest("form");
      if (form) return this.containerHasSensitiveControl(form);
      let node = el.parentElement;
      for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
        if (node.tagName === "BODY" || node.tagName === "HTML") break;
        if (this.containerHasSensitiveControl(node)) return true;
      }
      return false;
    }
    containerHasSensitiveControl(root) {
      const controls = root.querySelectorAll("input, textarea, select");
      for (const c of Array.from(controls)) {
        const type = (c.type || c.getAttribute("type") || "text").toLowerCase();
        if (type === "hidden" || type === "submit" || type === "button") continue;
        if (type === "password" || this.tokensIn(c) || this.patternsIn(c)) return true;
      }
      return false;
    }
    tokensIn(c) {
      const auto = (c.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/);
      return auto.some((t) => this.tokens.has(t));
    }
    patternsIn(c) {
      for (const a of ["name", "id", "autocomplete", "aria-label", "placeholder"]) {
        if (this.isSensitiveText(c.getAttribute(a))) return true;
      }
      return false;
    }
    labelTexts(el) {
      const out = [];
      const doc = el.ownerDocument;
      const labels = el.labels;
      if (labels) for (const l of Array.from(labels)) out.push(l.textContent ?? "");
      const wrap = el.closest("label");
      if (wrap) out.push(wrap.textContent ?? "");
      const by = el.getAttribute("aria-labelledby");
      if (by) for (const id of by.split(/\s+/)) out.push(doc.getElementById(id)?.textContent ?? "");
      return out;
    }
  };

  // src/shared/zones.ts
  function hostMatches(pattern, host) {
    if (pattern === host) return true;
    if (pattern.startsWith("*.")) return host.endsWith(pattern.slice(1)) && host.length > pattern.length - 1;
    return false;
  }
  function pickSite(cfg2, host, packs) {
    const h = host.toLowerCase();
    for (const s of cfg2.sites) {
      if (packs && packs.length && !packs.includes(s.pack)) continue;
      if (s.hosts.some((p) => hostMatches(p, h))) return s;
    }
    return null;
  }
  function safeQuery(root, selector) {
    try {
      return root.querySelector(selector) !== null;
    } catch {
      return false;
    }
  }
  function firstWhen(doc, rules) {
    for (const r of rules ?? []) if (safeQuery(doc, r.when)) return r.zone;
    return null;
  }
  var Zoner = class {
    constructor(cfg2, site) {
      this.cfg = cfg2;
      this.site = site;
      this.vocab = new Set(cfg2.vocabulary);
    }
    cfg;
    site;
    vocab;
    /** Zone for an element event (click, focus, copy, paste, element scroll). */
    forElement(el, role) {
      const marked = el.closest("[data-understudy-zone]")?.getAttribute("data-understudy-zone") ?? "";
      if (marked && this.vocab.has(marked)) return marked;
      if (this.site) {
        for (const rule of this.site.elements) {
          try {
            if (el.closest(rule.selector)) return rule.zone;
          } catch {
          }
        }
      }
      return this.generic(role);
    }
    /** Document-level scroll: the page's dominant zone. */
    forScroll(doc) {
      if (this.site) {
        const z = firstWhen(doc, this.site.page);
        if (z) return z;
      }
      return "doc";
    }
    forNav(doc) {
      if (!this.site) return void 0;
      return firstWhen(doc, this.site.nav) ?? this.site.nav_default;
    }
    /** Selectors that identify a zone: the explicit attribute plus the site's configured element selectors. */
    selectorsFor(zone) {
      if (!this.vocab.has(zone)) return [];
      const sels = [`[data-understudy-zone="${zone}"]`];
      for (const rule of this.site?.elements ?? []) if (rule.zone === zone) sels.push(rule.selector);
      return sels;
    }
    /** Task markers for a navigation: only element presence is tested, and only enum tokens come out. */
    markersFor(navZone, doc) {
      const mk = this.site?.markers;
      if (!mk) return void 0;
      const out = { progress: [] };
      if (mk.task_start && navZone === mk.task_start.zone) out.start = { idle_s: mk.task_start.idle_s };
      for (const p of mk.progress ?? []) if (safeQuery(doc, p.when) && !out.progress.includes(p.kind)) out.progress.push(p.kind);
      if (mk.task_end && safeQuery(doc, mk.task_end.when)) out.end = { reason: mk.task_end.reason };
      return out.start || out.progress.length || out.end ? out : void 0;
    }
    forTab(doc) {
      if (!this.site) return void 0;
      return firstWhen(doc, this.site.tab) ?? this.site.tab_default;
    }
    generic(role) {
      if (role === "searchbox") return "search_box";
      if (["textbox", "combobox", "spinbutton", "checkbox", "radio", "slider"].includes(role)) return "form_field";
      return void 0;
    }
  };

  // src/shared/dom.ts
  var INPUT_ROLE = {
    button: "button",
    submit: "button",
    reset: "button",
    image: "button",
    checkbox: "checkbox",
    radio: "radio",
    range: "slider",
    number: "spinbutton",
    search: "searchbox",
    email: "textbox",
    tel: "textbox",
    text: "textbox",
    url: "textbox",
    password: "textbox",
    date: "textbox",
    "datetime-local": "textbox",
    month: "textbox",
    time: "textbox",
    week: "textbox"
  };
  var TAG_ROLE = {
    a: "link",
    button: "button",
    select: "combobox",
    textarea: "textbox",
    img: "img",
    summary: "button",
    h1: "heading",
    h2: "heading",
    h3: "heading",
    h4: "heading",
    h5: "heading",
    h6: "heading",
    p: "paragraph",
    li: "listitem",
    td: "cell",
    th: "cell",
    tr: "row",
    table: "table",
    nav: "navigation",
    form: "form",
    main: "main",
    dialog: "dialog",
    option: "option",
    article: "article",
    pre: "text",
    label: "text"
  };
  var ROLE_RE2 = /^[a-z][a-z0-9_-]{0,31}$/;
  function roleOf(el) {
    const explicit = (el.getAttribute("role") ?? "").trim().toLowerCase().split(/\s+/)[0] ?? "";
    if (explicit && ROLE_RE2.test(explicit)) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "input") {
      const type = (el.type || el.getAttribute("type") || "text").toLowerCase();
      return INPUT_ROLE[type] ?? "textbox";
    }
    if (tag === "a" && !el.hasAttribute("href")) return "generic";
    if (tag === "select" && (el.multiple || el.size > 1)) return "listbox";
    const r = TAG_ROLE[tag];
    if (r) return r;
    if (el.isContentEditable) return "textbox";
    return "generic";
  }
  var INTERACTIVE_SELECTOR = 'a[href], button, input, select, textarea, summary, [role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], [role="textbox"], [role="searchbox"], [role="combobox"], [role="switch"], [role="option"], [tabindex]';
  function interactiveAncestor(el) {
    return el.closest(INTERACTIVE_SELECTOR);
  }
  function isFormField(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === "input") {
      const type = (el.type || "text").toLowerCase();
      return !["button", "submit", "reset", "image", "hidden"].includes(type);
    }
    if (tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return ["textbox", "searchbox", "combobox"].includes((el.getAttribute("role") ?? "").toLowerCase());
  }
  function squash(s, max = 80) {
    return (s ?? "").replace(/\s+/g, " ").trim().slice(0, max);
  }
  function accessibleName(el) {
    const doc = el.ownerDocument;
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const text2 = by.split(/\s+/).map((id) => doc.getElementById(id)?.textContent ?? "").join(" ");
      if (squash(text2)) return squash(text2);
    }
    const aria = squash(el.getAttribute("aria-label"));
    if (aria) return aria;
    const tag = el.tagName.toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea") {
      const labels = el.labels;
      if (labels && labels.length) {
        const t = squash(Array.from(labels).map((l) => l.textContent ?? "").join(" "));
        if (t) return t;
      }
      const type = (el.type || "").toLowerCase();
      if (["button", "submit", "reset"].includes(type)) return squash(el.value);
      if (type === "image") return squash(el.getAttribute("alt"));
      return squash(el.getAttribute("placeholder")) || squash(el.getAttribute("title")) || squash(el.getAttribute("name"));
    }
    if (tag === "img") return squash(el.getAttribute("alt")) || squash(el.getAttribute("title"));
    const text = squash(el.textContent);
    if (text) return text;
    return squash(el.getAttribute("title"));
  }
  function isVisible(el) {
    const he = el;
    if (he.hidden) return false;
    const win = el.ownerDocument.defaultView;
    if (win) {
      const cs = win.getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // src/content/capture.ts
  var SEARCH_NAME_RE = /^(q|query|search|s|keyword|keywords|term|terms)$/i;
  var SCROLL_MIN_RANGE_PX = 50;
  var SCROLL_THROTTLE_MS = 750;
  var FOCUS_DEDUPE_MS = 1e3;
  var SEARCH_DEDUPE_MS = 1500;
  var NAV_DEDUPE_MS = 400;
  function domainHashOf(win, salt2) {
    return hashDomain(salt2, win.location.host);
  }
  function installCapture(deps) {
    const { win, salt: salt2, matcher: matcher2, zoner: zoner2, emit } = deps;
    const doc = win.document;
    const now = deps.now ?? (() => Date.now());
    const requireTrusted = deps.requireTrusted ?? true;
    const isTop2 = deps.isTop ?? (() => {
      try {
        return win.top === win;
      } catch {
        return false;
      }
    })();
    const domain = () => domainHashOf(win, salt2);
    const trusted = (e) => !requireTrusted || e.isTrusted;
    const safe = (fn) => (e) => {
      try {
        fn(e);
      } catch {
      }
    };
    const describe = (raw, opts2 = {}) => {
      const interactive = interactiveAncestor(raw);
      const el = interactive ?? raw;
      if (matcher2.inSensitiveContext(el) || matcher2.inSensitiveContext(raw)) return null;
      if (opts2.interactiveOnly && !interactive) return null;
      const role = roleOf(el);
      const target = { role, domain_hash: domain() };
      if (interactive) {
        const name = accessibleName(interactive);
        if (name && !matcher2.isSensitiveText(name)) target.label_hash = hashLabel(salt2, name);
      }
      return { target, zone: zoner2.forElement(el, role) };
    };
    const withZone = (meta, zone) => {
      if (zone) meta.zone = zone;
      return meta;
    };
    const onClick = safe((e) => {
      if (!trusted(e) || !(e.target instanceof win.Element)) return;
      const d = describe(e.target);
      if (!d) return;
      emit({ type: "click", target: d.target, meta: withZone({}, d.zone) });
    });
    let lastFocus = { el: null, at: 0 };
    const onFocus = safe((e) => {
      if (!trusted(e) || !(e.target instanceof win.Element)) return;
      const el = e.target;
      if (!isFormField(el) && !el.matches(INTERACTIVE_SELECTOR)) return;
      const t = now();
      if (lastFocus.el === el && t - lastFocus.at < FOCUS_DEDUPE_MS) return;
      lastFocus = { el, at: t };
      const d = describe(el);
      if (!d) return;
      emit({ type: "focus", target: d.target, meta: withZone({}, d.zone) });
    });
    const lastBin = /* @__PURE__ */ new WeakMap();
    let lastScrollAt = -Infinity;
    const onScroll = safe((e) => {
      if (!trusted(e)) return;
      const t = now();
      if (t - lastScrollAt < SCROLL_THROTTLE_MS) return;
      const isDoc = e.target === doc || e.target === win;
      const scroller = isDoc ? doc.scrollingElement ?? doc.documentElement : e.target instanceof win.Element ? e.target : null;
      if (!scroller) return;
      const range = scroller.scrollHeight - scroller.clientHeight;
      if (!(range >= SCROLL_MIN_RANGE_PX)) return;
      const bin = Math.min(4, Math.max(0, Math.floor(scroller.scrollTop / range * 5)));
      if (lastBin.get(scroller) === bin) return;
      lastBin.set(scroller, bin);
      lastScrollAt = t;
      let target = { domain_hash: domain() };
      let zone;
      if (isDoc) zone = zoner2.forScroll(doc);
      else {
        const d = describe(scroller);
        if (!d) return;
        target = d.target;
        zone = d.zone;
      }
      emit({ type: "scroll", target, meta: withZone({ depth_bin: bin }, zone) });
    });
    const copyCandidates = (target) => {
      const out = [];
      if (target instanceof win.Element) out.push(target);
      const node = win.getSelection?.()?.anchorNode ?? null;
      const anchor = node ? node.nodeType === 1 ? node : node.parentElement : null;
      if (anchor) out.push(anchor);
      if (doc.activeElement) out.push(doc.activeElement);
      return out;
    };
    const onCopy = safe((e) => {
      if (!trusted(e)) return;
      const cands = copyCandidates(e.target);
      if (!cands.length || cands.some((c) => matcher2.inSensitiveContext(c))) return;
      const el = cands.find((c) => c !== doc.body && c !== doc.documentElement) ?? cands[0];
      const d = describe(el);
      if (!d) return;
      emit({ type: "copy", target: d.target, meta: withZone({}, d.zone) });
    });
    const onPaste = safe((e) => {
      if (!trusted(e) || !(e.target instanceof win.Element)) return;
      const d = describe(e.target);
      if (!d) return;
      emit({ type: "paste", target: d.target, meta: withZone({}, d.zone) });
    });
    const isSearchField = (el) => {
      if (el.tagName !== "INPUT" && el.getAttribute("role") !== "searchbox") return false;
      const type = (el.type || "").toLowerCase();
      if (type === "search" || el.getAttribute("role") === "searchbox") return true;
      if (!["text", ""].includes(type)) return false;
      return SEARCH_NAME_RE.test(el.getAttribute("name") ?? "") || SEARCH_NAME_RE.test(el.id) || /search/i.test(el.getAttribute("aria-label") ?? "") || /search/i.test(el.getAttribute("placeholder") ?? "");
    };
    let lastSearch = { q: "", at: -Infinity };
    const emitSearch = (field) => {
      if (matcher2.inSensitiveContext(field)) return;
      const raw = field.value ?? "";
      const q = raw.replace(/\s+/g, " ").trim();
      if (!q) return;
      const t = now();
      if (q === lastSearch.q && t - lastSearch.at < SEARCH_DEDUPE_MS) return;
      lastSearch = { q, at: t };
      const target = { role: "searchbox", domain_hash: domain() };
      const name = accessibleName(field);
      if (name && !matcher2.isSensitiveText(name)) target.label_hash = hashLabel(salt2, name);
      const zone = zoner2.forElement(field, "searchbox") ?? "search_box";
      emit({ type: "search", target, meta: { len: Math.min(q.length, 500), q_hash: hashQuery(salt2, q), zone } });
    };
    const onKeydown = safe((e) => {
      if (!trusted(e) || e.key !== "Enter" || !(e.target instanceof win.Element) || !isSearchField(e.target)) return;
      emitSearch(e.target);
    });
    const onSubmit = safe((e) => {
      if (!trusted(e) || !(e.target instanceof win.HTMLFormElement)) return;
      const form = e.target;
      const field = Array.from(form.querySelectorAll("input, [role=searchbox]")).find(isSearchField);
      if (field) emitSearch(field);
    });
    let lastNav = -Infinity;
    const emitNav = (spa) => {
      if (!isTop2) return;
      const t = now();
      if (t - lastNav < NAV_DEDUPE_MS) return;
      lastNav = t;
      const meta = { spa };
      const zone = zoner2.forNav(doc);
      if (zone) meta.zone = zone;
      const markers = zoner2.markersFor(zone, doc);
      emit({ type: "nav", target: { role: "document", domain_hash: domain() }, meta, ...markers ? { markers } : {} });
    };
    const onSpa = safe(() => emitNav(true));
    const opts = { capture: true, passive: true };
    doc.addEventListener("click", onClick, opts);
    doc.addEventListener("focusin", onFocus, opts);
    doc.addEventListener("scroll", onScroll, opts);
    win.addEventListener("scroll", onScroll, opts);
    doc.addEventListener("copy", onCopy, opts);
    doc.addEventListener("paste", onPaste, opts);
    doc.addEventListener("keydown", onKeydown, opts);
    doc.addEventListener("submit", onSubmit, opts);
    win.addEventListener("popstate", onSpa);
    win.addEventListener("hashchange", onSpa);
    const nav = win.navigation;
    nav?.addEventListener("navigatesuccess", onSpa);
    emitNav(false);
    return () => {
      doc.removeEventListener("click", onClick, true);
      doc.removeEventListener("focusin", onFocus, true);
      doc.removeEventListener("scroll", onScroll, true);
      win.removeEventListener("scroll", onScroll, true);
      doc.removeEventListener("copy", onCopy, true);
      doc.removeEventListener("paste", onPaste, true);
      doc.removeEventListener("keydown", onKeydown, true);
      doc.removeEventListener("submit", onSubmit, true);
      win.removeEventListener("popstate", onSpa);
      win.removeEventListener("hashchange", onSpa);
      nav?.removeEventListener("navigatesuccess", onSpa);
    };
  }

  // src/content/l1.ts
  function cssEscape(s) {
    return Array.from(s).map((c, i) => /[a-zA-Z0-9_-]/.test(c) ? i === 0 && /[0-9]/.test(c) ? `\\3${c} ` : c : `\\${c}`).join("");
  }
  function attrEscape(s) {
    return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  }
  var ID_SEGMENT = /^(\d{3,}|[0-9a-f]{8,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;
  function templatePath(pathname) {
    const segs = pathname.split("/").map((seg) => {
      if (!seg) return seg;
      const hasDigit = /\d/.test(seg);
      const hasLetter = /[a-z]/i.test(seg);
      if (ID_SEGMENT.test(seg) || hasDigit && hasLetter && seg.length >= 6) return "_id_";
      return seg.replace(/[^A-Za-z0-9._-]/g, "_");
    });
    const out = segs.join("/");
    return out.startsWith("/") ? out : `/${out}`;
  }
  function slotName(base, used) {
    let s = base.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 28);
    if (!s) s = "field";
    if (!/^[a-z]/.test(s)) s = `p_${s}`;
    let out = s;
    for (let i = 2; used.has(out); i++) out = `${s}_${i}`.slice(0, 31);
    used.add(out);
    return out;
  }
  function locate(el) {
    const doc = el.ownerDocument;
    const tag = el.tagName.toLowerCase();
    const unique = (sel) => {
      try {
        return doc.querySelectorAll(sel).length === 1;
      } catch {
        return false;
      }
    };
    if (el.id) {
      const sel = `#${cssEscape(el.id)}`;
      if (unique(sel)) return { selector: sel };
    }
    const name = el.getAttribute("name");
    if (name) {
      const sel = `${tag}[name="${attrEscape(name)}"]`;
      if (unique(sel)) return { selector: sel };
    }
    const tid = el.getAttribute("data-testid");
    if (tid) {
      const sel = `[data-testid="${attrEscape(tid)}"]`;
      if (unique(sel)) return { selector: sel };
    }
    const accName = accessibleName(el);
    if (accName && accName.length <= 60) {
      const role = roleOf(el);
      const same = Array.from(doc.querySelectorAll(tag)).filter((o) => roleOf(o) === role && accessibleName(o) === accName);
      if (same.length === 1 && role !== "generic") return { role, name: accName };
    }
    const parts = [];
    let node = el;
    for (let depth = 0; node && depth < 4 && node.tagName !== "BODY"; depth++, node = node.parentElement) {
      const parent = node.parentElement;
      const nodeTag = node.tagName.toLowerCase();
      if (!parent) {
        parts.unshift(nodeTag);
        break;
      }
      const sameTag = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
      parts.unshift(sameTag.length > 1 ? `${nodeTag}:nth-of-type(${sameTag.indexOf(node) + 1})` : nodeTag);
    }
    return { selector: parts.join(" > ").slice(0, 300) };
  }
  function installL1(deps) {
    const { win, matcher: matcher2, emit } = deps;
    const doc = win.document;
    const now = deps.now ?? (() => Date.now());
    const requireTrusted = deps.requireTrusted ?? true;
    const isTop2 = deps.isTop ?? (() => {
      try {
        return win.top === win;
      } catch {
        return false;
      }
    })();
    const started = now();
    const usedSlots = /* @__PURE__ */ new Set();
    const slotOf = /* @__PURE__ */ new WeakMap();
    const slotFor = (el) => {
      let s = slotOf.get(el);
      if (!s) {
        s = slotName(el.getAttribute("name") || el.id || accessibleName(el) || "field", usedSlots);
        slotOf.set(el, s);
      }
      return s;
    };
    const skip = () => deps.onSkipped?.();
    const ok = (e) => deps.active() && (!requireTrusted || e.isTrusted);
    const step = (partial) => emit({ ...partial, t_ms: Math.max(0, now() - started) });
    const safe = (fn) => (e) => {
      try {
        fn(e);
      } catch {
      }
    };
    const onClick = safe((e) => {
      if (!ok(e) || !(e.target instanceof win.Element)) return;
      const el = e.target.closest("a[href], button, input, select, summary, [role=button], [role=link], [role=tab], [role=menuitem]") ?? null;
      if (!el) return;
      if (matcher2.inSensitiveContext(el)) return skip();
      const tag = el.tagName.toLowerCase();
      const type = el.type?.toLowerCase();
      if (tag === "select" || tag === "input" && !["button", "submit", "reset", "image", "checkbox", "radio"].includes(type)) return;
      step({ op: "click", ...locate(el) });
    });
    const onChange = safe((e) => {
      if (!ok(e) || !(e.target instanceof win.Element)) return;
      const el = e.target;
      if (!isFormField(el)) return;
      if (matcher2.inSensitiveContext(el)) return skip();
      const tag = el.tagName.toLowerCase();
      const type = (el.type || "").toLowerCase();
      if (type === "checkbox" || type === "radio") return;
      if (tag === "select") step({ op: "select", ...locate(el), param: slotFor(el) });
      else step({ op: "fill", ...locate(el), param: slotFor(el), input_type: type || (tag === "textarea" ? "textarea" : "text") });
    });
    const emitGoto = () => {
      if (!isTop2 || !deps.active()) return;
      const url = `${win.location.origin}${templatePath(win.location.pathname)}`;
      if (/^https?:\/\/[A-Za-z0-9._:/?=&%#-]+$/.test(url)) step({ op: "goto", url });
    };
    doc.addEventListener("click", onClick, { capture: true, passive: true });
    doc.addEventListener("change", onChange, { capture: true, passive: true });
    win.addEventListener("popstate", emitGoto);
    emitGoto();
    return () => {
      doc.removeEventListener("click", onClick, true);
      doc.removeEventListener("change", onChange, true);
      win.removeEventListener("popstate", emitGoto);
    };
  }

  // src/content/rect.ts
  var MAX_CANDIDATES = 2500;
  function inViewport(win, r) {
    return r.bottom > 0 && r.right > 0 && r.top < win.innerHeight && r.left < win.innerWidth;
  }
  function resolveRect(win, want, deps) {
    const now = deps.now ?? (() => Date.now());
    const doc = win.document;
    if (want.zone !== void 0) return finish(win, zoneMatches(win, want.zone, deps), now);
    const candidates = Array.from(doc.querySelectorAll(`${INTERACTIVE_SELECTOR}, h1, h2, h3, label, [data-understudy-zone]`)).slice(0, MAX_CANDIDATES);
    const wantName = want.name !== void 0 ? normaliseLabel(want.name) : null;
    const matches = [];
    for (const el of candidates) {
      if (deps.matcher.inSensitiveContext(el)) continue;
      if (want.label_hash) {
        const name = accessibleName(el);
        if (!name || hashLabel(deps.salt, name) !== want.label_hash) continue;
      } else if (want.role && wantName !== null) {
        if (roleOf(el) !== want.role || normaliseLabel(accessibleName(el)) !== wantName) continue;
      } else continue;
      if (isVisible(el)) matches.push(el);
    }
    return finish(win, matches, now);
  }
  function zoneMatches(win, zone, deps) {
    const sels = deps.zoner?.selectorsFor(zone) ?? [];
    if (!sels.length) return [];
    let found = [];
    try {
      found = Array.from(win.document.querySelectorAll(sels.join(", ")));
    } catch {
      for (const sel of sels) {
        try {
          found.push(...Array.from(win.document.querySelectorAll(sel)));
        } catch {
        }
      }
    }
    return found.filter((el) => !deps.matcher.inSensitiveContext(el) && isVisible(el)).slice(0, MAX_CANDIDATES);
  }
  function finish(win, matches, now) {
    if (!matches.length) return { found: false, measured_at: now() };
    const best = matches.find((el) => inViewport(win, el.getBoundingClientRect())) ?? matches[0];
    const r = best.getBoundingClientRect();
    let x = r.left;
    let y = r.top;
    let top = win;
    try {
      while (top.frameElement && top.parent && top.parent !== top) {
        const fr = top.frameElement.getBoundingClientRect();
        x += fr.left + top.frameElement.clientLeft;
        y += fr.top + top.frameElement.clientTop;
        top = top.parent;
      }
    } catch {
    }
    const side = Math.max(0, (top.outerWidth - top.innerWidth) / 2);
    const chrome2 = Math.max(0, top.outerHeight - top.innerHeight - side);
    return {
      found: true,
      rect: { x, y, w: r.width, h: r.height },
      window_offset: { x: top.screenX + side, y: top.screenY + chrome2 },
      scroll: { x: top.scrollX, y: top.scrollY },
      dpr: top.devicePixelRatio || 1,
      // The raw window geometry, so the desktop app can work out the page zoom itself instead of trusting window_offset.
      viewport: { w: top.innerWidth, h: top.innerHeight },
      outer: { w: top.outerWidth, h: top.outerHeight },
      screen: { x: top.screenX, y: top.screenY },
      measured_at: now()
    };
  }

  // src/content/main.ts
  var matcher = new SensitiveMatcher(bundled_default.sensitive);
  var zoneConfig = bundled_default.zones;
  var store = chrome.storage.local;
  var cfg = null;
  var salt = "";
  var zoner = null;
  var stopCapture = null;
  var stopL1 = null;
  var l1Active = false;
  var appliedRole = "";
  var isTop = (() => {
    try {
      return window.top === window;
    } catch {
      return false;
    }
  })();
  var send = (msg) => void chrome.runtime.sendMessage(msg).catch(() => void 0);
  async function getSalt() {
    const got = await store.get(STORAGE_KEYS.salt);
    const s = got[STORAGE_KEYS.salt];
    if (typeof s === "string" && /^[0-9a-f]{32}$/.test(s)) return s;
    const r = await chrome.runtime.sendMessage({ kind: "get_salt" }).catch(() => null);
    return r?.salt ?? "";
  }
  function stop() {
    stopCapture?.();
    stopL1?.();
    stopCapture = stopL1 = null;
  }
  async function sync() {
    cfg = await loadConfig(store);
    const t = (await store.get(STORAGE_KEYS.l1Targets))[STORAGE_KEYS.l1Targets];
    l1Active = Array.isArray(t) && t.length > 0;
    if (!cfg.capturing) return stop();
    if (!salt) salt = await getSalt();
    if (!salt) return stop();
    if (appliedRole && appliedRole !== cfg.role) stop();
    appliedRole = cfg.role;
    zoner = new Zoner(zoneConfig, pickSite(zoneConfig, location.host, [cfg.role]));
    if (!stopCapture) {
      stopCapture = installCapture({ win: window, salt, matcher, zoner, emit: (record) => send({ kind: "record", record }) });
    }
    if (l1Active && !stopL1) {
      stopL1 = installL1({
        win: window,
        matcher,
        active: () => l1Active,
        emit: (step) => send({ kind: "l1", step }),
        onSkipped: () => send({ kind: "l1_skipped" })
      });
    } else if (!l1Active && stopL1) {
      stopL1();
      stopL1 = null;
    }
  }
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id || !cfg?.capturing || !salt || !zoner) return false;
    if (msg?.kind === "rect") {
      const want = msg.want;
      sendResponse(resolveRect(window, want, { salt, matcher, zoner }));
      return false;
    }
    if (msg?.kind === "page_info" && isTop) {
      sendResponse({ domain_hash: domainHashOf(window, salt), zone: zoner.forTab(document) });
      return false;
    }
    return false;
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes[STORAGE_KEYS.salt]) {
      salt = "";
      stop();
    }
    if (changes[STORAGE_KEYS.config] || changes[STORAGE_KEYS.l1Targets] || changes[STORAGE_KEYS.salt]) void sync();
  });
  void sync();
})();
