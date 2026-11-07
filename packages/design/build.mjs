// Builds design-system.html from design-system.src.html by inlining tokens.css and
// components.css (an Artifact cannot link local files) and generating the colour table.
// Usage: node packages/design/build.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const read = (f) => fs.readFileSync(path.join(dir, f), "utf8");
const tokens = read("tokens.css");
const components = read("components.css");
let html = read("design-system.src.html");

// -- parse tokens for the colour table --
function block(sel) {
  const i = tokens.indexOf(sel);
  const s = tokens.indexOf("{", i);
  let d = 1, j = s + 1;
  while (d) { if (tokens[j] === "{") d++; if (tokens[j] === "}") d--; j++; }
  return tokens.slice(s + 1, j - 1);
}
const parse = (b) => { const o = {}; for (const m of b.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) o[m[1]] = m[2]; return o; };
const light = parse(block(":root {"));
const dark = { ...light, ...parse(block(':root[data-theme="dark"]')) };
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lum = (h) => { const n = parseInt(h.slice(1), 16); return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255); };
const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

const rows = [
  ["bg", "Canvas", "fg"], ["panel", "Raised surface, for separate objects only", "fg"], ["sunk", "Inset wells, code, skeletons", "fg"],
  ["fg", "Text", "panel"], ["muted", "Secondary text", "panel"], ["line", "Hairlines", null], ["line-strong", "Axes, hover edges", null],
  ["control-line", "Edges of inputs and buttons", "panel"],
  ["accent", "The one accent: focus, links, primary action", "panel"],
  ["expert", "Expert trace, memory nodes", "panel"], ["novice", "Novice trace, skill nodes", "panel"],
  ["good", "Automation, success", "panel"], ["warn", "Caution, always with a label", "panel"], ["bad", "Time lost, cost, error", "panel"],
];
const cell = (t, k, against) => {
  if (!against) return '<span class="hex">decorative</span>';
  const r = ratio(t[k], t[against]);
  return `<span class="hex" style="color:var(--fg)">${r.toFixed(1)} : 1</span> <span class="pass">${r >= 4.5 ? "AA" : r >= 3 ? "3:1" : ""}</span>`;
};
const colourRows = rows.map(([k, means, against]) =>
  `<tr><td><span class="swatch" style="--_c:var(--${k})"></span></td><td><code>--${k}</code></td><td>${means}</td>` +
  `<td class="hex">${light[k]}</td><td class="hex">${dark[k]}</td><td>${cell(light, k, against)}</td><td>${cell(dark, k, against)}</td></tr>`
).join("\n");

html = html.replace("/*@tokens*/", tokens.replace(/^\/\*[\s\S]*?\*\/\n/, "")).replace("/*@components*/", components);
html = html.replace("<!--@colour-rows-->", colourRows);
fs.writeFileSync(path.join(dir, "design-system.html"), html);
console.log("design-system.html", (html.length / 1024).toFixed(0) + " KB");
