import { describe, expect, it } from "vitest";
import bannedFile from "../../../../../docs/knack-ux/banned-phrases.json";
import { SCREENS } from "../../router";
import { ABOUT, wordsOf } from "./about";

const banned = (bannedFile as { phrases: string[] }).phrases;

describe("About this screen", () => {
  it("has an entry for every screen, with what it is and where the numbers come from", () => {
    expect(Object.keys(ABOUT).sort()).toEqual([...SCREENS].sort());
    for (const id of SCREENS) {
      expect(ABOUT[id].what.length, id).toBeGreaterThan(10);
      expect(ABOUT[id].from.length, id).toBeGreaterThan(10);
    }
  });
  it("keeps each part short: one sentence for what, at most two for where from, and a one-sentence limit", () => {
    for (const id of SCREENS) {
      const a = ABOUT[id];
      expect(wordsOf(a.what), `${id} what`).toBeLessThanOrEqual(20);
      expect(wordsOf(a.from), `${id} from`).toBeLessThanOrEqual(40);
      expect(a.what.match(/[.!?]/g)?.length, `${id} what is one sentence`).toBe(1);
      if (a.limit) { expect(wordsOf(a.limit), `${id} limit`).toBeLessThanOrEqual(20); expect(a.limit.match(/[.!?]/g)?.length, `${id} limit is one sentence`).toBe(1); }
    }
  });
  it("uses none of the banned phrases and none of the jargon the worker screens avoid", () => {
    for (const id of SCREENS) {
      const t = Object.values(ABOUT[id]).join(" ").toLowerCase();
      for (const p of banned) expect(t, `${id}: ${p}`).not.toMatch(new RegExp(`\\b${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "i"));
      expect(t, id).not.toMatch(/\bdemo\b|understudy|\brung\b|\bledger\b|\bgenome\b|\boccurrence\b/);
    }
  });
  it("never claims that nothing leaves the laptop", () => {
    for (const id of SCREENS) expect(Object.values(ABOUT[id]).join(" "), id).not.toMatch(/nothing (ever )?leaves/i);
  });
  it("prints the honesty limits where they matter: Growth, Your data, Firm and Evidence", () => {
    expect(ABOUT.growth.limit).toMatch(/help needed, not expertise/);
    expect(ABOUT["your-data"].limit).toMatch(/cannot show what other software/);
    expect(ABOUT.firm.limit).toMatch(/not for evaluating individuals/);
    expect(ABOUT.evidence.limit).toMatch(/four people/);
  });
});
