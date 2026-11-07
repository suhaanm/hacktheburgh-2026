// Bundles the extension into dist/ (load that folder unpacked in Chrome).
//
//   npm run build                                   default build into dist/ (sandbox ports 7801 to 7803)
//   SANDBOX_PORT_A=7911 SANDBOX_PORT_B=7912 SANDBOX_PORT_C=7913 npm run build -- --out dist-sim
//   SANDBOX_PORT_A=7911 SANDBOX_PORT_B=7912 SANDBOX_PORT_C=7913 node scripts/build.mjs --out dist-sim   (no typecheck)
//
// The capture config is generated in memory and bundled in; the committed src/generated/bundled.json is rewritten
// only by a build with the default ports, so builds for different port triples never touch each other.
import { build } from "esbuild";
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_OUT, effectivePorts, generate, isDefaultPorts, portOverrides } from "./gen.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT_NAME = /^dist(-[A-Za-z0-9_-]{1,40})?$/;

/** Builds into outDir. `outDir` defaults to <extension>/dist; a CLI --out must be dist or dist-<name>. */
export async function buildExtension({ ports = {}, outDir = join(root, "dist"), logLevel = "info" } = {}) {
  const eff = effectivePorts(ports);
  const config = generate({ ports });
  const isDefault = isDefaultPorts(eff);
  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  const inlineConfig = {
    name: "inline-generated-config",
    setup(b) {
      b.onResolve({ filter: /generated[\\/]bundled\.json$/ }, () => ({ path: "bundled.json", namespace: "generated-config" }));
      b.onLoad({ filter: /.*/, namespace: "generated-config" }, () => ({ contents: JSON.stringify(config), loader: "json" }));
    },
  };
  await build({
    entryPoints: {
      content: join(root, "src/content/main.ts"),
      worker: join(root, "src/background/worker.ts"),
      popup: join(root, "src/popup/popup.ts"),
    },
    outdir: outDir,
    bundle: true,
    format: "iife",
    target: "chrome116",
    platform: "browser",
    sourcemap: false,
    minify: false,
    legalComments: "none",
    logLevel,
    plugins: [inlineConfig],
  });
  // Chrome match patterns ignore the port (http://127.0.0.1/* covers every port), so the manifest's permissions need no
  // change; a non-default build is told apart by its version_name.
  const manifest = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));
  if (!isDefault) manifest.version_name = `${manifest.version} sandbox ${Object.values(eff).join("/")}`;
  writeFileSync(join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
  cpSync(join(root, "popup.html"), join(outDir, "popup.html"));
  if (isDefault && resolve(outDir) === join(root, "dist")) {
    writeFileSync(DEFAULT_OUT, JSON.stringify(config, null, 2) + "\n");   // keep the committed default bundle in step
  }
  return { outDir, ports: eff, config, isDefault };
}

/** `--out dist-sim` to an absolute directory inside this extension; anything else is refused (the build empties it). */
export function resolveOutArg(name) {
  if (name === undefined) return join(root, "dist");
  if (!OUT_NAME.test(name)) throw new Error(`--out must be dist or dist-<name> (letters, digits, underscore, hyphen), got ${JSON.stringify(name)}`);
  const dir = resolve(root, name);
  const rel = relative(root, dir);
  if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("--out must stay inside the extension folder");
  return dir;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const argv = process.argv.slice(2);
    let name;
    for (let i = 0; i < argv.length; i++) {
      if (argv[i] === "--out") name = argv[++i];
      else throw new Error(`unknown argument ${argv[i]}`);
    }
    const res = await buildExtension({ ports: portOverrides(), outDir: resolveOutArg(name) });
    console.log("built", res.outDir, `(sandbox ports ${Object.values(res.ports).join(", ")})`);
  } catch (e) {
    console.error(`build: ${e.message}`);
    process.exit(2);
  }
}
