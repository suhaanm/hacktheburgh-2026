// The rules scripts/view-audit.mjs applies. Pure (no browser, no network) so they have their own tests (view-rules.test.mjs).
// The rule being enforced is docs/knack-ux/views.md: a worker sees only their own work and one experienced worker's way of doing the task, never
// other people, never a cohort or firm figure, never system internals; an admin sees the firm in aggregate.
//
// Two classes of text rule:
//   FIRM rules   run on the FULL text of the page (every text node, including a closed disclosure: the rule says "even in a closed disclosure");
//   INTERNALS    rules run on the VISIBLE text only (what is drawn), and never inside a disclosure whose heading starts with "Advanced"
//                (the one place a worker may reach the call list, one click deeper, inside Settings).
// A rule may name routes where it does not apply, with the reason: the audit prints the reasons, so an exemption is never silent.

/** "p_learn01" style person ids; a firm member's id. The worker's own id is passed in and never flagged. */
// A person id has a number in it (p_learn01, p_nov13, p_exp06, p_f_bp03, p_git_learner_1) or is one of the four named personas. Field names such as p_stuck are not ids.
const PERSON_ID = /\bp_(?:irregular|nightowl|ninetofive|shiftwkr)\b|\bp_(?:[a-z]+_)*[a-z]*\d+[a-z0-9_]*\b/gi;

export const FIRM_RULES = [
  { id: "person-label", re: /\b(?:BP|DA|PR|PG)-\d{2}\b/g, why: "a firm member's label (BP-07)" },
  { id: "cohort-figure", re: /\b(?:average|mean|median|typical)\s+(?:over|across|of|for)\s+(?:all|everyone|the\s+firm|your\s+colleagues|colleagues|the\s+team|other\s+(?:workers|learners|people))\b/gi, why: "an average over other people" },
  { id: "cohort-figure", re: /\bacross\s+(?:the|your)\s+(?:firm|team|company|organisation|organization)\b/gi, why: "a firm or team figure" },
  { id: "cohort-figure", re: /\bfirm[- ]?wide\b|\bwhole\s+firm\b|\bthe\s+firm\b/gi, why: "the firm" },
  { id: "colleagues", re: /\bcolleagues?\b|\bco-?workers?\b|\bteammates?\b/gi, why: "other people as a group" },
  { id: "people-count", re: /\b\d[\d,]*\s+(?:people|persons|colleagues|workers|learners|users|staff|employees|juniors|experts|members)\b/gi, why: "a count of people" },
  { id: "other-people", re: /\b(?:other|all|most|many)\s+(?:learners|workers|people|juniors|novices|users)\b|\beveryone\s+else\b/gi, why: "other people as a group" },
  { id: "peer-rank", re: /\b(?:percentile|leaderboard)\b|\b(?:top|bottom)\s+\d+\s?%|\branked?\s+(?:#|no\.?\s*)?\d+\b|\bbetter\s+than\s+\d+\s?%/gi, why: "a ranking against other people" },
];

export const INTERNALS_RULES = [
  { id: "model-name", re: /\b(?:gemini[\w.-]*|gpt[- ]?[\w.]+|openai|anthropic|claude|sonnet|haiku|opus|elevenlabs|llama|mistral|argon|gemma)\b/gi, why: "a model or provider name" },
  { id: "cost", re: /(?:US\$|\$|£|€)\s?\d|\b\d[\d,.]*\s?(?:USD|GBP|dollars|pence|cents)\b|\bcosts?\b|\bper\s+(?:million\s+)?tokens?\b|\b\d[\d,.]*\s?[kKmM]?\s+tokens?\b|\bspend(?:ing)?\s+(?:cap|limit)\b/gi, why: "a cost or token count" },
  { id: "run-id", re: /\br_[a-z0-9]{3,}(?:_[a-z0-9]+)*\b|\brun\s+(?:id\s*)?[#:]?\s*[0-9a-f]{6,}\b/gi, why: "a run id" },
  { id: "ledger", re: /\bledger\b/gi, why: "the ledger (only inside Settings, Advanced)" },
  { id: "hash", re: /\b[0-9a-f]{12,64}\b|\bsha-?(?:1|256)\b|\bhash(?:es)?\b/gi, why: "a hash" },
  { id: "evidence", re: /\bevidence\b/gi, why: "an evidence table or page", exempt: { "needs-you": "an approval's own screenshots and extracted values are the worker's own work", home: "the approval card on Home shows the same own evidence", today: "the Today screen links the approval's own evidence" } },
  { id: "limitations", re: /\blimitations?\b/gi, why: "a limitations register" },
  { id: "diagnostics", re: /\b(?:latency|egress\s+guard|diagnostics?|routing|call\s+log|model\s+log)\b/gi, why: "system diagnostics" },
];

/** The words the admin gate must carry, and the most text a gate may carry besides it. */
export const GATE = { re: /switch\s+to\s+admin|choose\s+admin|part\s+of\s+the\s+admin\s+view/i, maxChars: 200 };

const snippet = (text, m, pad = 38) => {
  const a = Math.max(0, m.index - pad);
  const b = Math.min(text.length, m.index + m[0].length + pad);
  return (a > 0 ? "…" : "") + text.slice(a, b).replace(/\s+/g, " ").trim() + (b < text.length ? "…" : "");
};

/** Every match of one rule in a text, as {rule, why, match, snippet}. At most `cap` per rule so one noisy page stays readable. */
export function scanRule(rule, text, cap = 3) {
  const out = [];
  const re = new RegExp(rule.re.source, rule.re.flags.includes("g") ? rule.re.flags : rule.re.flags + "g");
  let m;
  while ((m = re.exec(text)) && out.length < cap) {
    if (m[0] === "") { re.lastIndex++; continue; }
    // the size of a meeting on the worker's own calendar ("Meeting, 5 to 9 people") is their own data, not a count of colleagues
    if (rule.id === "people-count" && /meeting|call|workshop|session/i.test(text.slice(Math.max(0, m.index - 40), m.index))) continue;
    out.push({ rule: rule.id, why: rule.why, match: m[0], snippet: snippet(text, m) });
  }
  return out;
}

/**
 * The text violations of one worker page.
 * `texts`: { full, visible } (visible already without anything inside an "Advanced" disclosure);
 * `route`: the route id, for exemptions; `own`: { id, names[] } the worker's own person id and name(s), never flagged;
 * `names`: other people's full names (the firm's roster and the engine's name list).
 */
export function workerTextViolations({ full, visible }, { route, own = {}, names = [] }) {
  const out = [];
  for (const r of FIRM_RULES) for (const v of scanRule(r, full)) out.push({ ...v, where: "text" });
  const ownId = (own.id ?? "").toLowerCase();
  const ownNames = new Set((own.names ?? []).map((n) => n.toLowerCase()));
  for (const m of full.matchAll(PERSON_ID)) {
    if (m[0].toLowerCase() === ownId) continue;
    out.push({ rule: "person-id", why: "another person's id", match: m[0], snippet: snippet(full, m), where: "text" });
    if (out.filter((v) => v.rule === "person-id").length >= 3) break;
  }
  const lower = full.toLowerCase();
  let nn = 0;
  for (const name of names) {
    const n = name.toLowerCase();
    if (!n || ownNames.has(n) || nn >= 3) continue;
    const i = lower.indexOf(n);
    if (i >= 0 && !/\w/.test(lower[i - 1] ?? " ") && !/\w/.test(lower[i + n.length] ?? " ")) {
      out.push({ rule: "person-name", why: "another person's name", match: name, snippet: snippet(full, { index: i, 0: name }), where: "text" });
      nn++;
    }
  }
  for (const r of INTERNALS_RULES) {
    if (r.exempt && r.exempt[route]) continue;
    for (const v of scanRule(r, visible)) out.push({ ...v, where: "text" });
  }
  return out;
}

/** Collapse repeated violations of one rule into one line each (rule + first snippet + count). */
export function summarise(violations) {
  const by = new Map();
  for (const v of violations) {
    const k = `${v.where}|${v.rule}|${v.endpoint ?? ""}`;
    const e = by.get(k) ?? { ...v, count: 0 };
    e.count++;
    by.set(k, e);
  }
  return [...by.values()];
}

// ---------------------------------------------------------------------------------------------- API checks
/** An endpoint a worker page must never call: it returns firm or admin data. */
export const FIRM_ENDPOINTS = [/\/insights\/admin\b/, /\/hitlist\/firm\b/, /\/firm\b(?!-)/, /\/admin\//];
/** Endpoints that return system internals. A worker page calling one is a WARNING (the screen may fetch and not draw); Settings is allowed. */
export const INTERNAL_ENDPOINTS = [/\/models(?:\/|$)/, /\/evidence\b/, /\/privacy\/ledger/, /\/egress/, /\/audit\b/, /\/model_meter/];

export const isFirmEndpoint = (path) => FIRM_ENDPOINTS.some((r) => r.test(path));
export const isInternalEndpoint = (path) => INTERNAL_ENDPOINTS.some((r) => r.test(path));

/** Other people's identity inside an API response body. */
export function apiIdentityViolations(body, { own = {}, names = [] }) {
  const out = [];
  const ownId = (own.id ?? "").toLowerCase();
  for (const m of body.matchAll(/\bp_f_[a-z0-9_]+\b/gi)) {
    out.push({ rule: "person-id", why: "another person's id in the response", match: m[0], snippet: snippet(body, m), where: "api" });
    break;
  }
  for (const m of body.matchAll(PERSON_ID)) {
    if (m[0].toLowerCase() === ownId || /^p_f_/i.test(m[0])) continue;
    out.push({ rule: "person-id", why: "another person's id in the response", match: m[0], snippet: snippet(body, m), where: "api" });
    break;
  }
  for (const m of body.matchAll(/\b(?:BP|DA|PR|PG)-\d{2}\b/g)) {
    out.push({ rule: "person-label", why: "a firm member's label in the response", match: m[0], snippet: snippet(body, m), where: "api" });
    break;
  }
  const lower = body.toLowerCase();
  const ownNames = new Set((own.names ?? []).map((n) => n.toLowerCase()));
  for (const name of names) {
    const n = name.toLowerCase();
    if (!n || ownNames.has(n)) continue;
    const i = lower.indexOf(n);
    if (i >= 0) { out.push({ rule: "person-name", why: "another person's name in the response", match: name, snippet: snippet(body, { index: i, 0: name }), where: "api" }); break; }
  }
  return out;
}
