// node --test scripts/lib/view-rules.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { GATE, apiIdentityViolations, isFirmEndpoint, isInternalEndpoint, summarise, workerTextViolations } from "./view-rules.mjs";

const own = { id: "p_learn01", names: ["Sam Carter"] };
const rules = (text, route = "growth", names = ["Amara Okafor", "Mei Tan"]) => {
  const v = workerTextViolations({ full: text, visible: text }, { route, own, names });
  return [...new Set(v.map((x) => x.rule))].sort();
};

test("a worker's own page is clean", () => {
  assert.deepEqual(rules("Your week. You finished 14 steps without help. Your time on the cliff check is down 20 seconds against an experienced worker. p_learn01 Sam Carter"), []);
});

test("firm and cohort figures are caught", () => {
  assert.ok(rules("Average over all learners: 62%").includes("cohort-figure"));
  assert.ok(rules("Across the firm, 12 people repeat this").includes("people-count"));
  assert.ok(rules("Your colleagues do this faster").includes("colleagues"));
  assert.ok(rules("Better than 80% of workers").includes("peer-rank"));
  assert.ok(rules("Firm-wide").includes("cohort-figure"));
});

test("other people's names, labels and ids are caught, the worker's own are not", () => {
  assert.ok(rules("Amara Okafor needs help with the cliff check").includes("person-name"));
  assert.ok(rules("BP-07 is improving").includes("person-label"));
  assert.ok(rules("person p_f_bp03").includes("person-id"));
  assert.deepEqual(rules("Sam Carter, p_learn01"), []);
  assert.deepEqual(rules("Amaranth Okaforth"), []);                // not a whole-name match
});

test("system internals are caught on the visible text", () => {
  assert.ok(rules("Model: Gemini 2.5 Flash").includes("model-name"));
  assert.ok(rules("This call cost $0.02").includes("cost"));
  assert.ok(rules("Run r_demo_0001 finished").includes("run-id"));
  assert.ok(rules("Open the ledger").includes("ledger"));
  assert.ok(rules("sha 3f9a1c7b2d4e5f60").includes("hash"));
  assert.ok(rules("Limitations of this analysis").includes("limitations"));
  assert.ok(rules("Latency 420 ms").includes("diagnostics"));
});

test("an exemption is per route and per rule", () => {
  assert.ok(rules("See the evidence", "growth").includes("evidence"));
  assert.deepEqual(rules("See the evidence", "needs-you"), []);
});

test("closed-disclosure text counts for firm rules but not for internals", () => {
  const v = workerTextViolations({ full: "Your colleagues. Ledger rows.", visible: "Your day." }, { route: "settings", own, names: [] });
  assert.deepEqual([...new Set(v.map((x) => x.rule))], ["colleagues"]);
});

test("the gate", () => {
  assert.ok(GATE.re.test("Switch to Admin to see this."));
  assert.ok(!GATE.re.test("Firm overview"));
});

test("endpoint classes", () => {
  assert.ok(isFirmEndpoint("/engine/insights/admin/overview"));
  assert.ok(isFirmEndpoint("/engine/hitlist/firm?window=7"));
  assert.ok(!isFirmEndpoint("/engine/insights/worker?person=p_learn01"));
  assert.ok(!isFirmEndpoint("/engine/hitlist?window=7"));
  assert.ok(isInternalEndpoint("/engine/models/status"));
  assert.ok(!isInternalEndpoint("/engine/growth"));
});

test("api bodies", () => {
  const v = apiIdentityViolations('{"rows":[{"person":"p_f_bp03","name":"Mei Tan"}]}', { own, names: ["Mei Tan"] });
  assert.deepEqual(v.map((x) => x.rule).sort(), ["person-id", "person-name"]);
  assert.deepEqual(apiIdentityViolations('{"person":"p_learn01"}', { own, names: ["Mei Tan"] }), []);
});

test("the size of a meeting on the worker's own calendar is not a firm count", () => {
  assert.deepEqual(rules("Mon Meeting, 5 to 9 people, 08:00 to 08:15"), []);
  assert.ok(rules("12 people repeat this").includes("people-count"));
});

test("summarise folds repeats", () => {
  const s = summarise([{ where: "text", rule: "cost" }, { where: "text", rule: "cost" }, { where: "api", rule: "person-id", endpoint: "/x" }]);
  assert.equal(s.length, 2);
  assert.equal(s.find((x) => x.rule === "cost").count, 2);
});
