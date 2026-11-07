// Port-parameterised capture check: build the extension for a private sandbox port triple, start a private sandbox on
// those ports, load the build in a persistent Chromium context (new headless by default, SIM_HEADED=1 for a window) and
// confirm a click on the sandbox is captured WITH its zone. A control build for the default ports must NOT zone the
// same pages (otherwise the port parameterisation would be doing nothing). Stub engine on an ephemeral port; the shared
// sandbox on 7801 to 7803 and the real engine are never touched.
//
//   node spikes/ports_sim.mjs                         free ports are picked
//   SIM_PORTS=7911,7912,7913 node spikes/ports_sim.mjs
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import net from "node:net";
import { chromium } from "playwright";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { buildExtension } from "../scripts/build.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((res) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
const portFree = (p) => new Promise((res) => { const s = net.createServer(); s.once("error", () => res(false)); s.listen(p, "127.0.0.1", () => s.close(() => res(true))); });
async function until(cond, ms, label) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await cond()) return; } catch {} await sleep(150); } throw new Error(`timed out waiting for ${label}`); }
const Ctor = Ajv2020.default ?? Ajv2020;
const ajv = new Ctor({ strict: false, allErrors: true });
(addFormats.default ?? addFormats)(ajv);
const validEvent = ajv.compile(JSON.parse(readFileSync(join(repo, "packages/schema/event.schema.json"), "utf8")));

const report = { ok: false, steps: {}, problems: [] };
const tmp = mkdtempSync(join(tmpdir(), "understudy-ports-sim-"));
const simDist = join(root, `dist-simtest-${process.pid}`);
const defDist = join(root, `dist-simdefault-${process.pid}`);
let sandbox, stub, context;

async function pickPorts() {
  const want = (process.env.SIM_PORTS ?? "7911,7912,7913").split(",").map(Number);
  if (want.length === 3 && (await Promise.all(want.map(portFree))).every(Boolean)) return want;
  return [await freePort(), await freePort(), await freePort()];
}

async function runVariant(label, dist, ports, enginePort, events, extra) {
  const userDataDir = mkdtempSync(join(tmp, "profile-"));
  const headless = process.env.SIM_HEADED !== "1";
  context = await chromium.launchPersistentContext(userDataDir, {
    headless, ...(headless ? { channel: "chromium" } : {}), viewport: { width: 1100, height: 700 },
    args: [`--disable-extensions-except=${dist}`, `--load-extension=${dist}`, "--no-first-run", "--no-default-browser-check"],
  });
  try {
    let [sw] = context.serviceWorkers();
    if (!sw) sw = await context.waitForEvent("serviceworker", { timeout: 20000 });
    await until(() => sw.evaluate(async () => Boolean((await chrome.storage.local.get("salt")).salt)), 10000, "worker init");
    const person = `p_sim${label}`;
    await sw.evaluate(async ({ enginePort, person }) => {
      await chrome.storage.local.set({ config: { capturing: true, person, role: "benefits-processor", engine_url: `http://127.0.0.1:${enginePort}`, desktop_url: "http://127.0.0.1:1", identity_adopted: false } });
    }, { enginePort, person });
    await sleep(500);
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${ports[0]}/step/1`);
    await page.waitForSelector("#continue");
    await until(() => events.some((e) => e.person === person && e.type === "nav"), 20000, `the nav event (${label})`);
    await page.fill('[name="your_age"]', "36");       // a real field, in the household form
    await page.click("#continue");                     // a real click
    await until(() => events.some((e) => e.person === person && e.type === "click"), 15000, `the click event (${label})`);
    if (extra) await extra({ page, sw, person });
    await sleep(3000);
    return events.filter((e) => e.person === person);
  } finally {
    await context.close().catch(() => {});
    context = null;
  }
}

try {
  const ports = await pickPorts();
  report.ports = ports;
  // 1. builds: one for the private ports, one control for the defaults
  const sim = await buildExtension({ ports: { a: ports[0], b: ports[1], c: ports[2] }, outDir: simDist, logLevel: "silent" });
  const def = await buildExtension({ outDir: defDist, logLevel: "silent" });
  const simCode = readFileSync(join(simDist, "content.js"), "utf8");
  report.steps.build = {
    sim_has_private_hosts: ports.every((p) => simCode.includes(`127.0.0.1:${p}`)),
    sim_has_default_hosts: ["7801", "7802", "7803"].some((p) => simCode.includes(p)),
    sim_version_name: JSON.parse(readFileSync(join(simDist, "manifest.json"), "utf8")).version_name,
    default_is_default: def.isDefault && sim.isDefault === false,
  };
  // 2. a private sandbox on those ports (in-process cluster: its CLI ignores SANDBOX_PORT_*), and a stub engine
  const py = join(repo, ".venv", "bin", "python");
  sandbox = spawn(py, ["-c", `
import time
from understudy_agent.sandbox_sites.runner import SandboxCluster
c = SandboxCluster(ports={"a": ${ports[0]}, "b": ${ports[1]}, "c": ${ports[2]}}).start()
print("ready", flush=True)
while True:
    time.sleep(3600)
`], { cwd: repo, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, SANDBOX_PORT_A: String(ports[0]), SANDBOX_PORT_B: String(ports[1]), SANDBOX_PORT_C: String(ports[2]) } });
  await new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("sandbox did not start")), 30000);
    sandbox.stdout.on("data", (d) => { if (String(d).includes("ready")) { clearTimeout(t); res(); } });
    sandbox.on("exit", (c) => rej(new Error(`sandbox exited ${c}`)));
  });
  for (const p of ports) await until(async () => (await fetch(`http://127.0.0.1:${p}/healthz`)).ok, 10000, `sandbox ${p}`);
  const events = [];
  stub = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      res.setHeader("content-type", "application/json");
      if (req.method === "POST" && req.url === "/events") { const a = JSON.parse(body); events.push(...a); res.end(JSON.stringify({ accepted: a.length, rejected: [] })); }
      else if (req.url === "/routines") res.end("[]");
      else { res.statusCode = 404; res.end("{}"); }
    });
  });
  await new Promise((r) => stub.listen(0, "127.0.0.1", r));
  const enginePort = stub.address().port;

  // 3. the build for the private ports captures the click, with zones and task markers
  const got = await runVariant("on", simDist, ports, enginePort, events);
  const zones = (type) => got.filter((e) => e.type === type).map((e) => e.meta?.zone);
  report.steps.sim_build = {
    events: got.length, types: [...new Set(got.map((e) => e.type))].sort(),
    nav_zone: zones("nav"), click_zones: zones("click"), has_task_start: got.some((e) => e.type === "task_start"),
    task_id_on_all_events: got.every((e) => /^t_[0-9a-f]{12}$/.test(e.task_id ?? "")),
    schema_invalid: got.filter((e) => !validEvent(e)).length,
    page_text_found: ["Continue", "your_age", "Your age"].filter((t) => JSON.stringify(got).includes(t)),
  };
  // 3b. the reconciliation select on the case-note page: keyboard change is trusted and captured; a script's selectOption is not, until
  //     accept_synthetic is switched on; flush_ms 1000 gets it to the engine in about a second
  const sel = {};
  await (async () => {
    const eventsBefore = events.length;
    const ctx2Events = events;
    await runVariant("sel", simDist, ports, enginePort, events, async ({ page, sw, person }) => {
      const changed = () => events.filter((e) => e.person === person && e.type === "click" && e.meta?.changed === true);
      await page.goto(`http://127.0.0.1:${ports[0]}/casenote?case=CASE-1005`);
      await page.waitForSelector("#reconciliation");
      await sleep(1500);
      await page.focus("#reconciliation");
      await page.keyboard.press("d");                                      // type-ahead picks "Discrepancy": a trusted input and change
      await until(() => changed().length >= 1, 8000, "the keyboard change");
      sel.keyboard_change = changed().length;
      sel.keyboard_zone = changed()[0]?.meta?.zone;
      await page.selectOption("#reconciliation", "agree");                 // script-dispatched: untrusted (no focus, no click)
      await sleep(3500);
      sel.selectoption_default_counted = changed().length - sel.keyboard_change;
      await sw.evaluate(async () => { const cur = (await chrome.storage.local.get("config")).config; await chrome.storage.local.set({ config: { ...cur, accept_synthetic: true, flush_ms: 1000 } }); });
      await sleep(800);
      const n = changed().length;
      const t0 = Date.now();
      await page.selectOption("#reconciliation", "discrepancy");
      await until(() => changed().length > n, 6000, "the synthetic change after accept_synthetic");
      sel.accept_synthetic_latency_ms = Date.now() - t0;
      sel.accept_synthetic_zone = changed().at(-1)?.meta?.zone;
      sel.values_or_text_leaked = ["discrepancy", "agree", "Reconciliation", "Calculators"].filter((t) => JSON.stringify(events.filter((e) => e.person === person)).includes(t));
    }).catch((e) => { sel.error = String(e); });
  })();
  report.steps.select_change = sel;

  // 4. control: the DEFAULT build on the same private ports must not zone anything (it only knows 7801 to 7803)
  const ctl = await runVariant("off", defDist, ports, enginePort, events);
  report.steps.default_build_control = {
    events: ctl.length, zones: [...new Set(ctl.map((e) => e.meta?.zone).filter(Boolean))], has_task_start: ctl.some((e) => e.type === "task_start"),
  };

  const s = report.steps;
  if (!s.build.sim_has_private_hosts) report.problems.push("the build lacks the private hosts");
  if (s.build.sim_has_default_hosts) report.problems.push("the build still contains a default port");
  if (!s.sim_build.nav_zone.includes("calc_site")) report.problems.push("nav was not zoned calc_site on the private port");
  if (!s.sim_build.click_zones.includes("household_form")) report.problems.push("the click was not zoned household_form");
  if (!s.sim_build.has_task_start || !s.sim_build.task_id_on_all_events) report.problems.push("task markers did not fire on the private port");
  if (s.sim_build.schema_invalid || s.sim_build.page_text_found.length) report.problems.push("schema or privacy failure");
  // the default build may still give the generic base zones (form_field, search_box, doc) from ARIA roles, but no site zone and no task marker
  const generic = new Set(["form_field", "search_box", "doc"]);
  if (s.default_build_control.zones.some((z) => !generic.has(z)) || s.default_build_control.has_task_start) report.problems.push("the default build zoned a private port with a site zone: the control failed");
  if (!s.default_build_control.events) report.problems.push("the control captured nothing at all");
  const sc = s.select_change;
  if (sc.error) report.problems.push(`select check failed: ${sc.error}`);
  else {
    if (sc.keyboard_change !== 1 || sc.keyboard_zone !== "reconcile_control") report.problems.push("a keyboard change on the reconciliation select was not captured with its zone");
    if (sc.selectoption_default_counted !== 0) report.problems.push("a script-dispatched change was counted without accept_synthetic");
    if (sc.accept_synthetic_zone !== "reconcile_control") report.problems.push("with accept_synthetic the change was not captured with its zone");
    if (!(sc.accept_synthetic_latency_ms < 2200)) report.problems.push(`flush_ms 1000 did not deliver within 2.2 s (${sc.accept_synthetic_latency_ms} ms)`);
    if (sc.values_or_text_leaked.length) report.problems.push("a value or label leaked");
  }
  report.ok = report.problems.length === 0;
} catch (e) {
  report.error = String(e?.stack ?? e);
} finally {
  await context?.close().catch(() => {});
  try { sandbox?.kill("SIGTERM"); } catch {}
  try { stub?.close(); } catch {}
  await sleep(500);
  for (const d of [simDist, defDist, tmp]) rmSync(d, { recursive: true, force: true });
  report.cleanup = { dist_removed: !existsSync(simDist) && !existsSync(defDist), sandbox_killed: sandbox ? sandbox.killed : null };
}
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);
