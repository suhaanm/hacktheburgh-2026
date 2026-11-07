import { pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The script that gives the synthetic firm its made-up names (scripts/name-fixtures.mjs). Imported by path, so the .mjs needs no type file.
const here = dirname(fileURLToPath(import.meta.url));
const mod = (await import(/* @vite-ignore */ pathToFileURL(join(here, "..", "..", "scripts", "name-fixtures.mjs")).href)) as {
  NAMES: string[]; fnv1a: (s: string) => number; assignNames: (labels: string[]) => Map<string, string>;
};

const firm = (n: number) => Array.from({ length: n }, (_, i) => `BP-${String(i + 1).padStart(2, "0")}`);

describe("the naming rule for the synthetic firm", () => {
  it("has at least 80 distinct names, each a first and a last name", () => {
    expect(mod.NAMES.length).toBeGreaterThanOrEqual(80);
    expect(new Set(mod.NAMES).size).toBe(mod.NAMES.length);
    for (const n of mod.NAMES) expect(n).toMatch(/^[A-Z][A-Za-z'-]+ [A-Z][A-Za-z'-]+$/);
  });
  it("gives every person a name and never reuses one inside a firm", () => {
    const labels = [...firm(30), ...firm(18).map((l) => l.replace("BP", "DA")), ...firm(12).map((l) => l.replace("BP", "PG"))];
    const m = mod.assignNames(labels);
    expect(m.size).toBe(60);
    expect(new Set(m.values()).size).toBe(60);
  });
  it("is deterministic: the same labels give the same names, in any input order", () => {
    const labels = firm(40);
    const a = mod.assignNames(labels);
    const b = mod.assignNames([...labels].reverse());
    expect([...a.entries()].sort()).toEqual([...b.entries()].sort());
    expect(mod.assignNames(labels).get("BP-07")).toBe(a.get("BP-07"));
  });
  it("starts from a hash of the label, so a name is not tied to the order of the list", () => {
    expect(mod.fnv1a("BP-01")).not.toBe(mod.fnv1a("BP-02"));
    expect(mod.fnv1a("BP-01")).toBe(mod.fnv1a("BP-01"));
  });
  it("refuses a firm bigger than the list rather than reusing a name", () => {
    expect(() => mod.assignNames(firm(mod.NAMES.length + 1))).toThrow();
  });
});
