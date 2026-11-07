"use strict";
(() => {
  // generated-config:bundled.json
  var bundled_default = { sensitive: [{ description: "Fields that are NEVER recorded or read (CAP-4, SEC). Data, not code: extend freely. Matched case-insensitively as regex against field name, id, label, placeholder, autocomplete and aria-label.", patterns: ["pass(word|wd|code|phrase)?", "\\bpin\\b", "\\botp\\b", "one[- ]?time", "2fa|mfa|verification[- ]code|security[- ]code", "\\bcvv\\b|\\bcvc\\b|card[- ]?(number|no)|credit|debit", "\\biban\\b|sort[- ]?code|account[- ]?(number|no)|routing", "national[- ]?insurance|\\bni[- ]?(number|no)\\b|\\bnino\\b|\\bssn\\b|social[- ]security", "passport|driving[- ]?licen[cs]e|date[- ]of[- ]birth|\\bdob\\b", "secret|token|api[- ]?key|private[- ]key|seed[- ]phrase", "cc-number|cc-csc|cc-exp|current-password|new-password|one-time-code"], autocomplete_tokens: ["cc-number", "cc-csc", "cc-exp", "current-password", "new-password", "one-time-code"], input_types: ["password"] }, { description: "Benefits-processor additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Data, not code: extend freely. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["\\bnino\\b|national[- ]?insurance|\\bni[- ]?(no|number)\\b", "claimant[- ]?(name|surname|forename|address|phone|email)", "(partner|spouse|child|children|dependant)[- ]?(name|dob|date[- ]of[- ]birth)", "(home|postal|street)[- ]?address|\\bpostcode\\b|\\bpost[- ]?code\\b|\\bzip\\b", "\\bphone\\b|\\bmobile\\b|\\bemail\\b", "\\butr\\b|unique[- ]?taxpayer|tax[- ]?(code|reference)", "bank[- ]?(name|details)|payee|direct[- ]?debit", "medical|diagnos|health[- ]?condition|disability[- ]?(type|detail)|\\bpip\\b[- ]?(ref|reference)", "immigration|visa|biometric|right[- ]to[- ]rent|residence[- ]permit", "benefit[- ]?claim[- ]?(ref|reference|number)|universal[- ]?credit[- ]?(ref|id)"], autocomplete_tokens: ["street-address", "address-line1", "address-line2", "postal-code", "tel", "email", "bday"], input_types: ["password", "tel", "email"] }, { description: "Data-analyst additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["connection[- ]?string|dsn|jdbc", "warehouse[- ]?(user|password|key)|service[- ]?account|credentials?", "access[- ]?key|secret[- ]?key|bearer", "(customer|user|patient|employee)[- ]?(name|email|phone|address|id)", "\\bemail\\b|\\bphone\\b|\\bmobile\\b|\\bpostcode\\b|\\bpost[- ]?code\\b"], autocomplete_tokens: ["email", "tel", "street-address", "postal-code"], input_types: ["password", "email", "tel"] }, { description: "Programmer additions to the global sensitive-fields list. The effective list is the union of this file and packages/schema/sensitive_fields.json. Patterns are case-insensitive regexes over field name, id, label, placeholder, autocomplete and aria-label.", extends: "../../schema/sensitive_fields.json", patterns: ["personal[- ]?access[- ]?token|\\bpat\\b|deploy[- ]?key|ssh[- ]?key|gpg|signing[- ]?key", "env(ironment)?[- ]?(var|variable)s?[- ]?(value|secret)|\\.env", "client[- ]?secret|webhook[- ]?secret|bearer|authorization", "recovery[- ]?code|backup[- ]?code", "\\bemail\\b"], autocomplete_tokens: ["email"], input_types: ["password", "email"] }], zones: { vocabulary: ["calc_result", "calc_site", "case_note", "chart_panel", "check_box", "ci_log", "cliff_button", "cliff_panel", "code_editor", "code_view", "commit_box", "compare_view", "data_browser", "decision_btn", "diff_view", "doc", "docs_page", "export_panel", "form_field", "help", "household_form", "profile_panel", "query_edit", "query_result", "results_tabs", "run_control", "search_box", "sql_editor", "test_runner"], sites: [{ pack: "benefits-processor", id: "a", hosts: ["127.0.0.1:7911", "localhost:7911"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }, { zone: "calc_result", when: "#result-amount, #calc-total" }, { zone: "household_form", when: 'form input[type="hidden"]' }], tab: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }], page: [{ zone: "case_note", when: 'form[action^="/casenote"], #note-id, #cn-id' }, { zone: "calc_result", when: "#result-amount, #calc-total" }, { zone: "household_form", when: 'form[action^="/step"], form[action^="/result"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: "#result-amount, #calc-total" }, { kind: "note_field", when: "#note-status, #cn-state" }], task_end: { when: "#note-status, #cn-state", reason: "note_saved" } }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "case_note", selector: 'form[action^="/casenote"], #note-id, #note-status, #note-body, #cn-id, #cn-state, #cn-text' }, { zone: "calc_result", selector: "#result-amount, #result-status, #result-ref, #calc-total, #calc-outcome, #calc-reference" }, { zone: "household_form", selector: 'form[action^="/step"], form[action^="/result"]' }] }, { pack: "benefits-processor", id: "b", hosts: ["127.0.0.1:7912", "localhost:7912"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "calc_result", when: "table" }], page: [{ zone: "calc_result", when: "table" }, { zone: "household_form", when: 'form[action^="/calculate"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: "#estimate-monthly, #est-amount" }] }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "calc_result", selector: "table" }, { zone: "household_form", selector: 'form[action^="/calculate"]' }] }, { pack: "benefits-processor", id: "c", hosts: ["127.0.0.1:7913", "localhost:7913"], nav_default: "calc_site", tab_default: "results_tabs", nav: [{ zone: "calc_result", when: "table" }], page: [{ zone: "calc_result", when: "table" }, { zone: "household_form", when: 'form[action^="/results"]' }], markers: { task_start: { zone: "calc_site", idle_s: 120 }, progress: [{ kind: "result_read", when: '[data-testid="out-amount"], [data-testid="x-out-amount"]' }] }, elements: [{ zone: "cliff_button", selector: "#cliff-btn" }, { zone: "cliff_panel", selector: "#cliff-panel" }, { zone: "calc_result", selector: "table" }, { zone: "household_form", selector: 'form[action^="/results"]' }] }, { pack: "data-analyst", id: "warehouse", hosts: ["*.snowflakecomputing.com", "console.cloud.google.com", "*.databricks.com"], nav_default: "data_browser", tab_default: "compare_view", elements: [{ zone: "sql_editor", selector: '.monaco-editor, [role="textbox"][aria-label], .cm-editor' }, { zone: "run_control", selector: 'button[data-testid*="run"], button[aria-label*="Run"]' }, { zone: "query_result", selector: '[role="grid"], [role="table"], .results' }] }, { pack: "data-analyst", id: "notebook", hosts: ["colab.research.google.com", "app.hex.tech", "localhost:8888"], nav_default: "data_browser", tab_default: "compare_view", elements: [{ zone: "sql_editor", selector: ".cm-editor, .monaco-editor, .CodeMirror" }, { zone: "run_control", selector: 'button[aria-label*="Run"], .run-button' }, { zone: "query_result", selector: '.output_area, .jp-OutputArea, [role="table"]' }, { zone: "chart_panel", selector: "canvas, svg.plot, .output_png" }] }, { pack: "data-analyst", id: "sheet", hosts: ["docs.google.com"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "chart_panel", selector: '[aria-label*="Chart"], .chart-container' }] }, { pack: "data-analyst", id: "bi", hosts: ["*.looker.com", "app.powerbi.com", "*.tableau.com"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "chart_panel", selector: 'svg, canvas, [data-testid*="chart"]' }, { zone: "export_panel", selector: 'button[aria-label*="Export"], button[aria-label*="Download"]' }] }, { pack: "programmer", id: "git_host", hosts: ["github.com", "gitlab.com", "bitbucket.org"], nav_default: "code_view", tab_default: "compare_view", elements: [{ zone: "commit_box", selector: '#commit-changes-modal, form[action*="commit"], [data-testid="commit-button"]' }, { zone: "code_editor", selector: '.cm-editor, .monaco-editor, textarea[name="value"]' }, { zone: "diff_view", selector: '#files, .diff-view, [data-testid="diff"]' }, { zone: "code_view", selector: '#read-only-cursor-text-area, .blob-wrapper, [data-testid="code-view"], table.highlight' }] }, { pack: "programmer", id: "ci", hosts: ["*.circleci.com", "buildkite.com", "localhost:8080"], nav_default: "ci_log", tab_default: "compare_view", elements: [{ zone: "test_runner", selector: 'button[aria-label*="Re-run"], button[aria-label*="Rerun"], [data-testid*="rerun"]' }, { zone: "ci_log", selector: 'pre, .log, [data-testid*="log"]' }] }, { pack: "programmer", id: "tracker", hosts: ["*.atlassian.net", "linear.app"], nav_default: "doc", tab_default: "compare_view", elements: [{ zone: "form_field", selector: 'textarea, input[type="text"]' }] }, { pack: "programmer", id: "docs", hosts: ["docs.python.org", "developer.mozilla.org", "stackoverflow.com", "*.readthedocs.io"], nav_default: "docs_page", tab_default: "docs_page", elements: [{ zone: "docs_page", selector: "main, article, #content, .answercell" }] }] } };

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

  // src/popup/popup.ts
  var store = chrome.storage.local;
  var $ = (id) => document.getElementById(id);
  var roles = [...new Set(bundled_default.zones.sites.map((s) => s.pack))];
  async function render() {
    const cfg = await loadConfig(store);
    const status = await chrome.runtime.sendMessage({ kind: "popup_status" }).catch(() => null);
    const on = $("on");
    on.checked = cfg.capturing;
    $("state").textContent = cfg.capturing ? "Capture is on" : "Capture is off";
    const sel = $("role");
    $("role-row").hidden = $("role-row-label").hidden = cfg.identity_adopted;
    $("who").textContent = cfg.identity_adopted ? `${cfg.person} (from Understudy)` : `${cfg.person} (local until you onboard)`;
    if (!sel.options.length) for (const r of roles) sel.add(new Option(r, r));
    sel.value = roles.includes(cfg.role) ? cfg.role : roles[0] ?? "";
    $("queued").textContent = String(status?.queued ?? 0);
    $("sent").textContent = String(status?.stats.accepted ?? 0);
    $("l1").textContent = status?.l1_targets.length ? `on (${status.l1_targets.length})` : "off";
    $("desk").textContent = status?.desktop_reachable ? "connected" : "not seen";
    $("err").textContent = status?.stats.last_error ? `Last problem: ${status.stats.last_error}` : "";
  }
  $("on").addEventListener("change", async (e) => {
    const cfg = await loadConfig(store);
    await store.set({ [STORAGE_KEYS.config]: { ...cfg, capturing: e.target.checked } });
    await render();
  });
  $("role").addEventListener("change", async (e) => {
    const cfg = await loadConfig(store);
    await store.set({ [STORAGE_KEYS.config]: { ...cfg, role: e.target.value } });
  });
  void render();
  setInterval(() => void render(), 2e3);
})();
