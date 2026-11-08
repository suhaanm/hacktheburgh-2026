import { afterEach, describe, expect, it } from "vitest";
import {
  NAME_KEY, NAME_MAX, NAME_RULE, adoptEngineName, checkName, cleanName, earlierRoles, getDisplayName, initialOf, profileChange, resetDisplayName,
  roleLabel, roleWords, setDisplayName,
} from "./profile";

describe("a name", () => {
  it("is trimmed, collapsed to single spaces, and may be nothing at all", () => {
    expect(checkName("  Amara   Okafor ")).toEqual({ ok: true, name: "Amara Okafor" });
    for (const empty of ["", "   ", "\n\t", null, undefined, "\u202e"]) expect(checkName(empty), JSON.stringify(empty)).toEqual({ ok: true, name: null });
  });
  it("takes letters of any script, spaces, hyphens, apostrophes and full stops, starting with a letter", () => {
    for (const n of ["Amara Okafor", "Jean-Luc O'Brien", "María José", "Zoë Müller", "Dr. Who", "O’Neil", "李雷", "Ольга Иванова", "محمد علي", "Åsa", "Sinéad", "Ng"]) {
      expect(checkName(n), n).toEqual({ ok: true, name: n });
    }
  });
  it("refuses digits, symbols, emoji, a leading mark and anything past 60 characters, with the rule, and never cuts a name silently", () => {
    for (const bad of ["R2D2", "Amara 7", "👍", "Amara 👍", "-Amara", "'Neil", ".Dr", "a@b.co", "<b>Amara</b>", "Amara; DROP TABLE", "x".repeat(NAME_MAX + 1)]) {
      expect(checkName(bad), bad).toEqual({ ok: false, message: NAME_RULE });
    }
    expect(checkName("x".repeat(NAME_MAX))).toEqual({ ok: true, name: "x".repeat(NAME_MAX) });
    expect(checkName(42 as never)).toEqual({ ok: false, message: NAME_RULE });
  });
  it("drops control characters and bidirectional overrides, so text cannot read backwards or span lines", () => {
    expect(checkName("Amara\u202eOkafor")).toEqual({ ok: true, name: "Amara Okafor" });
    expect(checkName("Amara\nOkafor")).toEqual({ ok: true, name: "Amara Okafor" });
    expect(checkName("Amara\u0000Okafor")).toEqual({ ok: true, name: "Amara Okafor" });
  });
  it("cleanName keeps a good stored value and refuses a stale or hand-edited one", () => {
    expect(cleanName("Amara")).toBe("Amara");
    expect(cleanName("R2D2")).toBeNull();
    expect(cleanName(null)).toBeNull();
  });
  it("gives the avatar one letter: the first letter, upper-cased, in any script", () => {
    expect(initialOf("amara")).toBe("A");
    expect(initialOf("élodie")).toBe("É");
    expect(initialOf("李雷")).toBe("李");
    expect(initialOf("")).toBeNull();
    expect(initialOf(null)).toBeNull();
  });
});

describe("a role as words", () => {
  const roles = [{ id: "benefits-processor", name: "UK benefits processor" }, { id: "programmer", name: "Programmer" }];
  it("uses the pack's name when the roles are known, else the id as words, else nothing", () => {
    expect(roleLabel("benefits-processor", roles)).toBe("UK benefits processor");
    expect(roleLabel("data-analyst", roles)).toBe("Data analyst");
    expect(roleLabel("data-analyst", null)).toBe("Data analyst");
    expect(roleLabel(null, roles)).toBeNull();
    expect(roleLabel("", roles)).toBeNull();
    expect(roleWords("a_b-c")).toBe("A b c");
    expect(roleWords("---")).toBeNull();
  });
  it("offers earlier work only under another role that has some", () => {
    expect(earlierRoles({ role: "programmer", roles: [{ role: "programmer", n: 40 }, { role: "benefits-processor", n: 12 }] })).toEqual(["benefits-processor"]);
    expect(earlierRoles({ role: "programmer", roles: [{ role: "programmer", n: 40 }, { role: "data-analyst", n: 0 }] })).toEqual([]);
    expect(earlierRoles(null)).toEqual([]);
    expect(earlierRoles({})).toEqual([]);
  });
});

describe("what a save sends", () => {
  it("sends only what changed, and nothing when nothing did (so the form just closes)", () => {
    expect(profileChange({ role: "a", name: "X" }, { role: "a", name: "X" })).toBeNull();
    expect(profileChange({ role: "a", name: "X" }, { role: "b", name: "X" })).toEqual({ role: "b" });
    expect(profileChange({ role: "a", name: "X" }, { role: "a", name: "Y" })).toEqual({ name: "Y" });
    expect(profileChange({ role: "a", name: "X" }, { role: "b", name: "Y" })).toEqual({ role: "b", name: "Y" });
  });
  it("sends an empty name to clear one, and never an empty role", () => {
    expect(profileChange({ role: "a", name: "X" }, { role: "a", name: null })).toEqual({ name: "" });
    expect(profileChange({ role: "a", name: null }, { role: null, name: null })).toBeNull();
    expect(profileChange({ role: null, name: null }, { role: "b", name: null })).toEqual({ role: "b" });
  });
});

describe("the name store", () => {
  afterEach(() => { resetDisplayName(); delete (globalThis as { window?: unknown }).window; });
  const withStorage = () => {
    const store = new Map<string, string>();
    (globalThis as unknown as { window: unknown }).window = { localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) } };
    return store;
  };
  it("keeps a good name on the device, forgets it for nothing, and refuses a bad one without changing what is kept", () => {
    const store = withStorage();
    expect(setDisplayName("Amara Okafor")).toBe("Amara Okafor");
    expect(store.get(NAME_KEY)).toBe("Amara Okafor");
    expect(getDisplayName()).toBe("Amara Okafor");
    expect(setDisplayName("R2D2")).toBeNull();
    expect(store.has(NAME_KEY)).toBe(false);
    setDisplayName("Amara");
    expect(setDisplayName("")).toBeNull();
    expect(store.has(NAME_KEY)).toBe(false);
  });
  it("follows the engine's word, including when the engine has none", () => {
    withStorage();
    adoptEngineName("Amara");
    expect(getDisplayName()).toBe("Amara");
    adoptEngineName(null);
    expect(getDisplayName()).toBeNull();
  });
  it("lasts for the page even when storage is blocked", () => {
    (globalThis as unknown as { window: unknown }).window = { localStorage: { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } } };
    expect(setDisplayName("Amara")).toBe("Amara");
    expect(getDisplayName()).toBe("Amara");
  });
});
