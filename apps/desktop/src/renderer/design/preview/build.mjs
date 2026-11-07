// Generates docs/design-preview/index.html: one self-contained page (inline CSS, JS, fonts), no network.
// Usage: node src/renderer/design/preview/build.mjs   (uses the repo's typescript and @fontsource packages)
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const design = resolve(here, '..');
const repo = resolve(design, '../../..');
const root = repo;
const req = createRequire(join(root, 'package.json'));
const ts = req('typescript');
if (typeof ts.transpileModule !== 'function') throw new Error('typescript with transpileModule is required (TypeScript 6 or older)');

const read = (p) => readFileSync(p, 'utf8');
const font = (pkg, file) => readFileSync(req.resolve(`@fontsource/${pkg}/files/${file}`)).toString('base64');
const face = (family, weight, b64) =>
  `@font-face{font-family:'${family}';font-style:normal;font-weight:${weight};font-display:swap;src:url(data:font/woff2;base64,${b64}) format('woff2');}`;

const fonts = [
  face('Atkinson Hyperlegible', 400, font('atkinson-hyperlegible', 'atkinson-hyperlegible-latin-400-normal.woff2')),
  face('Atkinson Hyperlegible', 700, font('atkinson-hyperlegible', 'atkinson-hyperlegible-latin-700-normal.woff2')),
  face('OpenDyslexic', 400, font('opendyslexic', 'opendyslexic-latin-400-normal.woff2')),
  face('OpenDyslexic', 700, font('opendyslexic', 'opendyslexic-latin-700-normal.woff2')),
].join('\n');

// Artifact contract: dark tokens also apply under the system preference when no explicit data-theme is set.
let tokens = read(join(design, 'tokens.css'));
const darkRe = /:root\[data-theme='dark'\] \{([\s\S]*?)\n\}/;
const dark = darkRe.exec(tokens);
if (!dark) throw new Error('dark block not found in tokens.css');
tokens = tokens.replace(darkRe, `@media (prefers-color-scheme: dark) {\n  :root:not([data-theme='light']):not([data-high-contrast='true']) {${dark[1].replace(/\n/g, '\n  ')}\n  }\n}\n:root[data-theme='dark'] {${dark[1]}\n}`);

const transpile = (file) =>
  ts.transpileModule(read(file), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText.replace(/^export /gm, '');

const html = `<title>Alongside UI Preview</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
${fonts}
${tokens}
${read(join(design, 'components.css'))}
${read(join(here, 'preview.css'))}
</style>
<div class="al-app pv" id="app"></div>
<script>
${transpile(join(design, 'levels.ts'))}
${transpile(join(design, '../dock/profile.ts'))}
${transpile(join(design, 'annotation-style.ts'))}
${read(join(here, 'preview.js'))}
</script>
`;
const out = join(repo, 'docs/design-preview/index.html');
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, html);
console.log(`wrote ${out} (${(html.length / 1024).toFixed(0)} KB)`);
