// Generates the extension's bundled config from the repo's packs and schema:
//   sensitive: the global sensitive-fields list plus each pack's additions (the extension never records any of them)
//   zones:     vocabulary and per-site selector -> zone config (CAP-4: zones are enums, no page text)
// tasks/sites.yaml stays the single source; its ports are the defaults. A port triple can be overridden with
// SANDBOX_PORT_A, SANDBOX_PORT_B and SANDBOX_PORT_C (site ids a, b, c) so several private sandbox worlds can run at once.
//
//   node scripts/gen.mjs                       writes src/generated/bundled.json from the defaults (7801 to 7803)
//   node scripts/gen.mjs --defaults            ignores any SANDBOX_PORT_* in the environment
//   SANDBOX_PORT_A=7911 SANDBOX_PORT_B=7912 SANDBOX_PORT_C=7913 node scripts/gen.mjs --out /tmp/bundled.7911.json
//
// With non-default ports, --out is required so the committed default bundle is never overwritten by accident.
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");
const packsDir = join(repo, "packages", "packs");
export const DEFAULT_OUT = join(here, "..", "src", "generated", "bundled.json");

function packIds() {
  return readdirSync(packsDir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(packsDir, d.name, "pack.yaml")))
    .map((d) => d.name)
    .sort();
}

/** The sandbox calculators' default ports from tasks/sites.yaml: { a: 7801, b: 7802, c: 7803 }. */
export function defaultPorts() {
  for (const id of packIds()) {
    const pack = YAML.parse(readFileSync(join(packsDir, id, "pack.yaml"), "utf8"));
    if (!pack.tasks) continue;
    const ts = YAML.parse(readFileSync(join(packsDir, id, pack.tasks, "sites.yaml"), "utf8"));
    return Object.fromEntries(ts.sites.filter((s) => s.kind === "calculator").map((s) => [s.id, s.port]));
  }
  return {};
}

/** Overrides from SANDBOX_PORT_A/B/C. Returns only what is set. Throws on a value that is not a usable port. */
export function portOverrides(env = process.env) {
  const out = {};
  for (const id of ["a", "b", "c"]) {
    const raw = env[`SANDBOX_PORT_${id.toUpperCase()}`];
    if (raw === undefined || raw === "") continue;
    if (!/^[0-9]{4,5}$/.test(raw) || Number(raw) < 1024 || Number(raw) > 65535) {
      throw new Error(`SANDBOX_PORT_${id.toUpperCase()}=${JSON.stringify(raw)} is not a port from 1024 to 65535`);
    }
    out[id] = Number(raw);
  }
  return out;
}

/** The ports a build will use: the overrides laid over the defaults. Throws if two sites would share one. */
export function effectivePorts(overrides = {}) {
  const ports = { ...defaultPorts(), ...overrides };
  const seen = new Map();
  for (const [id, port] of Object.entries(ports)) {
    if (seen.has(port)) throw new Error(`sites ${seen.get(port)} and ${id} would both use port ${port}`);
    seen.set(port, id);
  }
  return ports;
}

export function isDefaultPorts(ports) {
  const d = defaultPorts();
  return Object.keys(d).every((id) => ports[id] === d[id]);
}

export function generate({ ports = {} } = {}) {
  const eff = effectivePorts(ports);
  const sensitive = [JSON.parse(readFileSync(join(repo, "packages", "schema", "sensitive_fields.json"), "utf8"))];
  const vocabulary = new Set();
  const sites = [];
  for (const id of packIds()) {
    const dir = join(packsDir, id);
    const pack = YAML.parse(readFileSync(join(dir, "pack.yaml"), "utf8"));
    const sfPath = join(dir, pack.risk_classes.sensitive_fields);
    sensitive.push(JSON.parse(readFileSync(sfPath, "utf8")));
    const mapping = YAML.parse(readFileSync(join(dir, pack.cogs.mapping), "utf8"));
    for (const z of mapping.zones) vocabulary.add(z);
    for (const cs of mapping.capture_sites ?? []) sites.push({ pack: id, ...cs });
    if (pack.tasks) {
      const ts = YAML.parse(readFileSync(join(dir, pack.tasks, "sites.yaml"), "utf8"));
      for (const s of ts.sites) {
        if (!s.capture) continue;
        const port = eff[s.id] ?? s.port;
        sites.push({
          pack: id,
          id: s.id,
          hosts: [`${ts.host}:${port}`, `localhost:${port}`],
          ...s.capture,
        });
      }
    }
  }
  return { sensitive, zones: { vocabulary: [...vocabulary].sort(), sites } };
}

function parseArgs(argv) {
  const out = { defaults: false, out: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--defaults") out.defaults = true;
    else if (argv[i] === "--out") out.out = argv[++i];
    else throw new Error(`unknown argument ${argv[i]}`);
  }
  return out;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const args = parseArgs(process.argv.slice(2));
    const ports = args.defaults ? {} : portOverrides();
    const eff = effectivePorts(ports);
    if (!isDefaultPorts(eff) && !args.out) {
      throw new Error("non-default ports: pass --out <file> so the committed src/generated/bundled.json is not overwritten");
    }
    const out = args.out ? resolve(args.out) : DEFAULT_OUT;
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, JSON.stringify(generate({ ports }), null, 2) + "\n");
    console.log("wrote", out, `(sandbox ports ${Object.values(eff).join(", ")})`);
  } catch (e) {
    console.error(`gen: ${e.message}`);
    process.exit(2);
  }
}
