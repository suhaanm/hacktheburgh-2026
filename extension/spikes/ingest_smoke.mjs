// Live ingest smoke test: the REAL extension (headed Chromium via Playwright) against a REAL engine process and the
// REAL sandbox sites on 7801-7803, with the consent toggle on. The engine is a second instance of the same code on an
// ephemeral port with a throwaway UNDERSTUDY_HOME and UNDERSTUDY_DATA_DIR, so nothing touches ~/.understudy or the
// shared data/ directory. Person ids are p_smoke*. Everything throwaway is deleted at the end.
// Usage: npm run build && node spikes/ingest_smoke.mjs
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, symlinkSync, readFileSync, readdirSync, writeFileSync, rmSync, existsSync, openSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";
import { chromium } from "playwright";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const repo = resolve(root, "..");
const dist = join(root, "dist");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const report = { ok: false, steps: {}, problems: [] };
const problem = (msg) => { report.problems.push(msg); };

const Ctor = Ajv2020.default ?? Ajv2020;
const ajv = new Ctor({ strict: false, allErrors: true });
(addFormats.default ?? addFormats)(ajv);
const validEvent = ajv.compile(JSON.parse(readFileSync(join(repo, "packages/schema/event.schema.json"), "utf8")));

const freePort = () => new Promise((res) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
async function until(cond, ms, label) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await cond()) return; } catch {} await sleep(250); } throw new Error(`timed out waiting for ${label}`); }
const j = async (url, init) => { const r = await fetch(url, init); const text = await r.text(); let body; try { body = JSON.parse(text); } catch { body = text; } return { status: r.status, body }; };

// the sandbox specs (selectors, field order) and the case inputs come straight from the repo
const specs = JSON.parse(execFileSync("uv", ["run", "--offline", "--package", "understudy-agent", "python", "-c",
  "import json;from understudy_agent.sandbox_sites.specs import SITES;print(json.dumps({s:{'fields':v.fields('v1'),'steps':[list(x) for x in v.steps],'buttons':list(v.buttons('v1')),'style':v.selector_style} for s,v in SITES.items()}))"],
  { cwd: repo, encoding: "utf8" }));
const cases = JSON.parse(readFileSync(join(repo, "evals/cases/households_20.json"), "utf8")).cases;
const HH = cases.find((c) => c.household.archetype === "savings_tariff_band") ?? cases[0];
const SELECTS = new Set(["adults", "limited_capability", "tenure", "bedrooms"]);
const selFor = (site, param) => {
  const key = specs[site].fields[param];
  return specs[site].style === "testid" ? `[data-testid="${key}"]` : specs[site].style === "id" ? `#${key}` : `[name="${key}"]`;
};
const PACE = Number(process.env.SMOKE_PACE_MS ?? 0);   // pause per field: 1500 gives roughly a minute per person
async function fillParam(page, site, param) {
  if (PACE) await sleep(PACE);
  const sel = selFor(site, param);
  const value = HH.site_inputs[site][param];
  if (SELECTS.has(param)) await page.selectOption(sel, value);
  else await page.fill(sel, value);
}
async function runCalculator(page, site, { slow = 0 } = {}) {
  const base = `http://127.0.0.1:${{ a: 7801, b: 7802, c: 7803 }[site]}`;
  await page.goto(site === "a" ? `${base}/step/1` : `${base}/`);
  const pages = specs[site].steps;
  for (let i = 0; i < pages.length; i++) {
    for (const p of pages[i]) { await fillParam(page, site, p); if (slow) await sleep(slow); }
    await page.click(specs[site].buttons[i]);
    if (i < pages.length - 1) await page.waitForLoadState("load");
  }
  await page.waitForSelector("#cliff-btn", { timeout: 15000 });
  await page.mouse.wheel(0, 400);
}
const openCliff = async (page) => { await page.click("#cliff-btn"); await page.waitForSelector("#cliff-panel li", { timeout: 15000 }); await page.mouse.wheel(0, 300); };
async function saveDraft(page, { reconcile }) {
  await page.goto(`http://127.0.0.1:7801/casenote?case=${HH.household.case_ref}`);
  for (const [id, v] of [["#result-a", "1"], ["#result-b", "2"], ["#result-c", "3"]]) await page.fill(id, v);
  if (reconcile) await page.selectOption("#reconciliation", "discrepancy");
  await page.fill("#note-text", "smoke-test note");
  await page.click("#save-draft");           // never "Submit to claimant record"
  await page.waitForSelector("#note-status");
}

const expertFlow = async (context, page) => {
  await runCalculator(page, "a"); await openCliff(page);
  const pb = await context.newPage();
  await runCalculator(pb, "b"); await openCliff(pb);
  for (let i = 0; i < 2; i++) { await page.bringToFront(); await sleep(700); await pb.bringToFront(); await sleep(700); }
  await pb.close();
  await page.bringToFront();
  await saveDraft(page, { reconcile: true });
};
const partialFlow = async (_context, page) => {      // stops mid-task: result read, cliff opened, note not saved
  await runCalculator(page, "a"); await openCliff(page);
};
const noviceFlow = async (_context, page) => {
  await runCalculator(page, "a", { slow: 400 });
  await page.goto("http://127.0.0.1:7801/step/1"); await sleep(1500);   // starts over: re-enters the household
  await fillParam(page, "a", "adults"); await fillParam(page, "a", "adult1_age");
  await sleep(2500);
  await saveDraft(page, { reconcile: false });
};

// ---------------------------------------------------------------------------------------------- engine (isolated)
const tmp = mkdtempSync(join(tmpdir(), "understudy-smoke-"));
const home = join(tmp, "home"), data = join(tmp, "data");
mkdirSync(home, { recursive: true }); mkdirSync(data, { recursive: true });
symlinkSync(join(repo, "data", "synthetic"), join(data, "synthetic"));   // read-only use, so /health warm-up has its inputs
const enginePort = await freePort();
const engineUrl = `http://127.0.0.1:${enginePort}`;
const logFd = openSync(join(tmp, "engine.log"), "a");
// run the venv's own entry point (not `uv run`, whose wrapper process would outlive a kill of its child)
const bin = join(repo, ".venv", "bin", "understudy");
const [cmd, args] = existsSync(bin) ? [bin, ["serve", "--port", String(enginePort)]] : ["uv", ["run", "--offline", "--package", "understudy-agent", "understudy", "serve", "--port", String(enginePort)]];
const engine = spawn(cmd, args, {
  cwd: repo, detached: true, stdio: ["ignore", logFd, logFd],
  env: { ...process.env, UNDERSTUDY_HOME: home, UNDERSTUDY_DATA_DIR: data, UNDERSTUDY_MOCK: "1" },
});
let context;
const userDataDir = mkdtempSync(join(tmpdir(), "understudy-smoke-browser-"));
const PERSONS = { exp1: "p_smokeexp1", exp2: "p_smokeexp2", nov1: "p_smokenov1", nov2: "p_smokenov2", part1: "p_smokepart1" };
try {
  await until(async () => (await j(`${engineUrl}/health`)).status === 200, 90000, "the isolated engine");
  report.steps.engine = { url: engineUrl, health: (await j(`${engineUrl}/health`)).body.ok, home_is_throwaway: home.startsWith(tmpdir()) };
  for (const s of [7801, 7802, 7803]) await until(async () => (await j(`http://127.0.0.1:${s}/healthz`)).status === 200, 60000, `sandbox site ${s}`);

  const headless = process.env.S3_HEADLESS === "1";
  context = await chromium.launchPersistentContext(userDataDir, {
    headless, ...(headless ? { channel: "chromium" } : {}), viewport: { width: 1200, height: 800 },
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, "--no-first-run", "--no-default-browser-check"],
  });
  let [sw] = context.serviceWorkers();
  if (!sw) sw = await context.waitForEvent("serviceworker", { timeout: 15000 });
  await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get("salt")).salt)), 10000, "worker init");
  const setConfig = (patch) => sw.evaluate(async (p) => { const cur = (await chrome.storage.local.get("config")).config ?? {}; await chrome.storage.local.set({ config: { ...cur, ...p } }); }, patch);
  const getConfig = () => sw.evaluate(async () => (await chrome.storage.local.get("config")).config);
  const flush = async (ms = 4500) => sleep(ms);   // batch timer is 2 s

  // consent toggle on, local identity (no onboarding yet) for the four smoke people
  const runPerson = async (key, flow, role = "benefits-processor") => {
    await setConfig({ capturing: false }); await sleep(300);
    await setConfig({ person: PERSONS[key], role, engine_url: engineUrl, desktop_url: "http://127.0.0.1:1", identity_adopted: false, capturing: true });
    await sleep(800);
    const page = await context.newPage();
    const t0 = Date.now();
    await flow(context, page);
    await flush();
    await page.close();
    return Date.now() - t0;
  };
  report.steps.run_ms = {};
  report.steps.run_ms.exp1 = await runPerson("exp1", expertFlow);
  report.steps.run_ms.exp2 = await runPerson("exp2", expertFlow);
  report.steps.run_ms.nov1 = await runPerson("nov1", noviceFlow);
  report.steps.run_ms.nov2 = await runPerson("nov2", noviceFlow);
  report.steps.run_ms.part1 = await runPerson("part1", partialFlow);
  await setConfig({ capturing: false });

  // ------------------------------------------------------------------------------------------ what landed on disk
  const realDir = join(data, "real");
  const byPerson = {};
  for (const person of Object.values(PERSONS)) {
    const dir = join(realDir, person);
    const files = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".jsonl")) : [];
    const rows = files.flatMap((f) => readFileSync(join(dir, f), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)));
    byPerson[person] = { files, rows };
  }
  const all = Object.values(byPerson).flatMap((p) => p.rows);
  const blob = JSON.stringify(all);
  const typeCount = {}; const zoneCount = {};
  for (const e of all) { typeCount[e.type] = (typeCount[e.type] ?? 0) + 1; const z = e.meta?.zone; if (z) zoneCount[z] = (zoneCount[z] ?? 0) + 1; }
  const invalid = all.filter((e) => !validEvent(e));
  const tasks = {};
  for (const [p, v] of Object.entries(byPerson)) {
    const rows = v.rows.slice().sort((a, b) => a.t.localeCompare(b.t));
    const ids = [...new Set(rows.map((e) => e.task_id).filter(Boolean))];
    tasks[p] = {
      task_ids: ids, types: Object.fromEntries(["task_start", "progress", "task_end"].map((t) => [t, rows.filter((e) => e.type === t).length])),
      first_event_is_task_start: rows[0]?.type === "task_start", untagged_events: rows.filter((e) => !e.task_id).length,
      progress_kinds: rows.filter((e) => e.type === "progress").map((e) => e.meta.kind),
      ends_with_task_end: rows.at(-1)?.type === "task_end",
    };
  }
  report.steps.tasks = tasks;
  const PAGE_TEXT = ["Check cliff edges", "Calculate", "Continue", "Estimated Universal Credit", "GOV-", "T2U-", "ET-", "Case note", "Save draft", "smoke-test note",
    HH.household.case_ref, "Your age", "Total savings", "Household", "Submit to claimant"];
  report.steps.disk = {
    per_person_rows: Object.fromEntries(Object.entries(byPerson).map(([p, v]) => [p, v.rows.length])),
    files: Object.fromEntries(Object.entries(byPerson).map(([p, v]) => [p, v.files])),
    total: all.length, types: typeCount, zones: zoneCount, schema_invalid: invalid.length,
    page_text_found: PAGE_TEXT.filter((s) => blob.includes(s)),
    url_like_found: /https?:|\/\/|127\.0\.0\.1|localhost/.test(blob),
    all_origin_real_actor_human_browser: all.every((e) => e.origin === "real" && e.actor === "human" && e.source === "browser"),
    hashed_shapes_ok: all.every((e) => (!e.target?.label_hash || /^h:[0-9a-f]{12}$/.test(e.target.label_hash)) && (!e.target?.domain_hash || /^d:[0-9a-f]{12}$/.test(e.target.domain_hash))),
    domain_hashes: [...new Set(all.map((e) => e.target?.domain_hash).filter(Boolean))].length,
  };
  if (invalid.length) problem(`schema-invalid rows on disk: ${JSON.stringify(validEvent.errors).slice(0, 300)}`);
  if (report.steps.disk.page_text_found.length) problem(`page text found in stored events: ${report.steps.disk.page_text_found}`);

  // ------------------------------------------------------------------------------------------ engine reads
  const person = PERSONS.exp1;
  const ev = await j(`${engineUrl}/events?partition=real&person=${person}&limit=5000`);
  report.steps.get_events = { status: ev.status, count: ev.body.events?.length };
  const rp = await j(`${engineUrl}/replay?person=${person}&partition=real&speed=20`);
  const last = rp.body.frames?.[rp.body.frames.length - 1];
  report.steps.replay = { status: rp.status, frames: rp.body.total_frames, duration_s: rp.body.duration_s, final_counts: last?.state?.counts, last_cog: last?.state?.last_cog, error: rp.status !== 200 ? rp.body : undefined };
  const rpPart = await j(`${engineUrl}/replay?person=${PERSONS.part1}&partition=real&speed=20`);
  report.steps.replay_partial = { status: rpPart.status, frames: rpPart.body.total_frames, final_counts: rpPart.body.frames?.[rpPart.body.frames.length - 1]?.state?.counts, last_task: rpPart.body.frames?.[rpPart.body.frames.length - 1]?.state?.task };
  const rpNov = await j(`${engineUrl}/replay?person=${PERSONS.nov1}&partition=real&speed=20`);
  report.steps.replay_novice = { status: rpNov.status, frames: rpNov.body.total_frames, final_counts: rpNov.body.frames?.[rpNov.body.frames.length - 1]?.state?.counts };

  const noRoster = await j(`${engineUrl}/genome/benefits-household-entry?person=${PERSONS.nov1}&partition=real`);
  report.steps.genome_without_roster = { status: noRoster.status, code: noRoster.body?.error?.code };
  mkdirSync(realDir, { recursive: true });
  writeFileSync(join(realDir, "roster.json"), JSON.stringify({ [PERSONS.exp1]: "expert", [PERSONS.exp2]: "expert", [PERSONS.nov1]: "novice", [PERSONS.nov2]: "novice" }));
  const g = await j(`${engineUrl}/genome/benefits-household-entry?person=${PERSONS.nov1}&partition=real`);
  const gd = g.body.data;
  report.steps.genome = {
    status: g.status, error: g.status !== 200 ? g.body : undefined, meta: g.body.meta,
    expert_person: gd?.expert_person, novice_segments: gd?.novice?.segments?.length, expert_segments: gd?.expert?.segments?.length,
    novice_cogs: gd?.novice?.segments?.map((s) => s.cog), expert_cogs: gd?.expert?.segments?.map((s) => s.cog),
    ops: gd?.alignment ? Object.fromEntries(["match", "mismatch", "gap_expert", "gap_novice"].map((o) => [o, gd.alignment.filter((a) => a.op === o).length])) : null,
    total_gap_s: gd?.total_gap_s, total_gap_ci: gd?.total_gap_ci, waterfall: gd?.waterfall, controls: gd?.controls,
  };
  const tr = await j(`${engineUrl}/graph/transitions?task=benefits-household-entry&partition=real`);
  report.steps.transitions = { status: tr.status, nodes: tr.body.data?.nodes?.length, edges: tr.body.data?.edges?.length, missing_for_novice: tr.body.data?.edges?.filter((e) => e.missing_for_novice).length, error: tr.status !== 200 ? tr.body : undefined };
  const co = await j(`${engineUrl}/coach/next?person=${PERSONS.part1}&dry=true`);
  report.steps.coach_next = { status: co.status, body: co.body };
  const coDone = await j(`${engineUrl}/coach/next?person=${PERSONS.nov1}&dry=true`);
  report.steps.coach_next_finished_task = { status: coDone.status, reason_codes: coDone.body.data?.reason_codes, action: coDone.body.data?.action };
  const co2 = await j(`${engineUrl}/coach/next?person=${PERSONS.exp1}&dry=true`);
  report.steps.coach_next_expert = { status: co2.status, body: co2.body.data ?? co2.body };

  // ------------------------------------------------------------------------------------------ identity adoption
  const before = await j(`${engineUrl}/identity`);
  const q = await j(`${engineUrl}/onboarding/questions?role=benefits-processor`);
  const answers = {};
  for (const qu of q.body.questions) {
    if (qu.kind === "multi") answers[qu.id] = qu.options.filter((o) => o.default).map((o) => o.value);
    else if (qu.kind === "single") answers[qu.id] = (qu.options.find((o) => o.default) ?? qu.options[0]).value;
    else answers[qu.id] = qu.default_hours ?? { start: "09:00", end: "17:30", days: ["mon", "tue", "wed", "thu", "fri"] };
  }
  const ob = await j(`${engineUrl}/onboarding`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ person: "p_smokeid1", role: "benefits-processor", answers }) });
  const idNow = await j(`${engineUrl}/identity`);
  report.steps.identity = { before_status: before.status, onboarding_status: ob.status, onboarding_person: ob.body.person, identity_after: idNow.body };
  await setConfig({ person: PERSONS.exp1, role: "programmer", engine_url: engineUrl, identity_adopted: false, capturing: false });
  await sleep(500);
  await setConfig({ capturing: true });     // turning capture on triggers a consent and identity refresh
  await until(async () => (await getConfig()).identity_adopted === true, 15000, "identity adoption").catch(() => {});
  const cfgAfter = await getConfig();
  report.steps.identity.extension_config_after = { person: cfgAfter.person, role: cfgAfter.role, identity_adopted: cfgAfter.identity_adopted };
  // browse a little more: events must now carry the engine's person
  const page2 = await context.newPage();
  await runCalculator(page2, "a"); await flush();
  await page2.close();
  const idEvents = await j(`${engineUrl}/events?partition=real&person=p_smokeid1&limit=5000`);
  report.steps.identity.events_under_engine_person = idEvents.body.events?.length;
  const stray = await j(`${engineUrl}/events?partition=real&person=${PERSONS.exp1}&limit=5000`);
  report.steps.identity.exp1_events_total_after = stray.body.events?.length;

  const memoryFile = join(home, "memory.md");
  report.steps.throwaway_home_used = { memory_file_exists: existsSync(memoryFile) };

  // the real repo data dir must be untouched
  report.steps.repo_data_real_exists_after = existsSync(join(repo, "data", "real"));
  report.ok = report.problems.length === 0;
} catch (e) {
  report.error = String(e?.stack ?? e);
} finally {
  await context?.close().catch(() => {});
  try { engine.kill("SIGTERM"); } catch {}
  try { process.kill(-engine.pid, "SIGTERM"); } catch {}
  await sleep(1500);
  report.engine_still_running_after_cleanup = (() => { try { process.kill(engine.pid, 0); return true; } catch { return false; } })();
  report.engine_log_tail = existsSync(join(tmp, "engine.log")) ? readFileSync(join(tmp, "engine.log"), "utf8").split("\n").filter((l) => /error|traceback|warning|exception/i.test(l)).slice(-12) : [];
  rmSync(tmp, { recursive: true, force: true });
  rmSync(userDataDir, { recursive: true, force: true });
  report.cleanup = { throwaway_removed: !existsSync(tmp), repo_data_real_p_smoke: existsSync(join(repo, "data", "real")) ? readdirSync(join(repo, "data", "real")).filter((n) => n.startsWith("p_smoke")) : [] };
}
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);
