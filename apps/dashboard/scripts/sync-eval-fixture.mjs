// Copies the eval harness's evals/report.json into src/fixtures/eval-report.json, so the demo (and wifi off) shows the same numbers
// the engine serves at GET /eval/report. Drops sections and bulky inner keys the Evidence page never reads, to keep the bundle small.
// Usage: node scripts/sync-eval-fixture.mjs   (from apps/dashboard; the report must exist: run `make eval` first)
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "..", "evals", "report.json");
const dst = join(here, "..", "src", "fixtures", "eval-report.json");
if (!existsSync(src)) { console.error(`No report at ${src}. Run make eval first.`); process.exit(1); }
const report = JSON.parse(readFileSync(src, "utf8"));

const dropSections = ["skills", "policy_gate", "forecast"];
const dropKeys = {
  pooling: ["datasets"],
  redteam: ["by_category", "defended_by", "layer_contribution"],
  hazard: ["per_person", "secondary", "vs_planted"],
  ope: ["diagnostics", "other_targets", "replications"],
  routing: ["calibration", "baselines", "feature_ablation", "fixed_review_budget", "random_review_at_budget", "resplits", "risk_control_naive", "held_out", "risk_control"],
  presence: ["per_persona", "summary"],
  ski_rental: ["sweep"],
  agent_claims: ["model", "baselines", "operating_point"],
};
for (const k of dropSections) delete report.sections[k];
for (const [sec, keys] of Object.entries(dropKeys)) for (const k of keys) if (report.sections[sec]) delete report.sections[sec][k];
delete report.run; // timings only
writeFileSync(dst, JSON.stringify(report) + "\n");
console.log(`wrote ${dst} (${(JSON.stringify(report).length / 1024).toFixed(0)} KB from ${(readFileSync(src).length / 1024).toFixed(0)} KB)`);
