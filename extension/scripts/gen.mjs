// Generates src/generated/bundled.json from the repo's packs and schema:
//   sensitive: the global sensitive-fields list plus each pack's additions (the extension never records any of them)
//   zones:     vocabulary and per-site selector -> zone config (CAP-4: zones are enums, no page text)
// Run by `npm run build` and `npm test`. The output is committed so reviewers can see what ships.
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");
const packsDir = join(repo, "packages", "packs");

export function generate() {
  const sensitive = [JSON.parse(readFileSync(join(repo, "packages", "schema", "sensitive_fields.json"), "utf8"))];
  const vocabulary = new Set();
  const sites = [];
  const packs = readdirSync(packsDir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(packsDir, d.name, "pack.yaml")))
    .map((d) => d.name)
    .sort();
  for (const id of packs) {
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
        sites.push({
          pack: id,
          id: s.id,
          hosts: [`${ts.host}:${s.port}`, `localhost:${s.port}`],
          ...s.capture,
        });
      }
    }
  }
  return { sensitive, zones: { vocabulary: [...vocabulary].sort(), sites } };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = join(here, "..", "src", "generated", "bundled.json");
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(generate(), null, 2) + "\n");
  console.log("wrote", out);
}
