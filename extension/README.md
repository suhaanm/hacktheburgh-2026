# Understudy capture extension
Private sandbox ports: `SANDBOX_PORT_A=7911 SANDBOX_PORT_B=7912 SANDBOX_PORT_C=7913 npm run build -- --out dist-sim` (defaults 7801 to 7803 come from `packages/packs/benefits-processor/tasks/sites.yaml`; `npm run gen` needs `--out <file>` for non-default ports; `--out` must be `dist` or `dist-<name>`).
Load `dist-sim` unpacked; `node spikes/ports_sim.mjs` builds, starts a private sandbox and checks in Chromium that a click is captured with its zone; `npm test` covers gen and build.
