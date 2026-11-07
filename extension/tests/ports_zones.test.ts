import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { resolveRect } from "../src/content/rect";
import { roleOf } from "../src/shared/dom";
import { pickSite, Zoner, type ZoneConfig } from "../src/shared/zones";
import { matcher, SALT, zoneConfig } from "./helpers";

// the generator is plain node; load it without type declarations
const genPath = "../scripts/gen.mjs";
const gen = (await import(/* @vite-ignore */ genPath)) as { generate: (o: { ports: Record<string, number> }) => { zones: ZoneConfig } };
const sim = gen.generate({ ports: { a: 7911, b: 7912, c: 7913 } }).zones;
const dir = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "sandbox");
function load(name: string): void {
  const doc = new DOMParser().parseFromString(readFileSync(join(dir, `${name}.html`), "utf8"), "text/html");
  document.documentElement.innerHTML = doc.documentElement.innerHTML;
}
const zonerOn = (cfg: ZoneConfig, host: string) => new Zoner(cfg, pickSite(cfg, host, ["benefits-processor"]));
const q = (s: string) => document.querySelector(s) as HTMLElement;

describe("a build for another port triple still maps zones, markers and rects", () => {
  it("picks the site by the new host and not by the old ones", () => {
    expect(pickSite(sim, "127.0.0.1:7911", ["benefits-processor"])?.id).toBe("a");
    expect(pickSite(sim, "localhost:7912", ["benefits-processor"])?.id).toBe("b");
    expect(pickSite(sim, "127.0.0.1:7913", ["benefits-processor"])?.id).toBe("c");
    for (const old of ["127.0.0.1:7801", "127.0.0.1:7802", "127.0.0.1:7803"]) expect(pickSite(sim, old, ["benefits-processor"]), old).toBeNull();
    // and the default build is the mirror image
    expect(pickSite(zoneConfig, "127.0.0.1:7911", ["benefits-processor"])).toBeNull();
  });

  it("zones: the same page gives the same zones on 7911 as on 7801", () => {
    for (const [host, defHost, page] of [["127.0.0.1:7911", "127.0.0.1:7801", "a-result-v1"], ["127.0.0.1:7912", "127.0.0.1:7802", "b-result-v2"], ["127.0.0.1:7913", "127.0.0.1:7803", "c-form-v1"]] as const) {
      load(page);
      const s = zonerOn(sim, host), d = zonerOn(zoneConfig, defHost);
      expect(s.forNav(document)).toBe(d.forNav(document));
      expect(s.forScroll(document)).toBe(d.forScroll(document));
      expect(s.forTab(document)).toBe(d.forTab(document));
      const el = q("#cliff-btn") ?? q("input, select");
      expect(s.forElement(el, roleOf(el))).toBe(d.forElement(el, roleOf(el)));
    }
    load("a-result-v1");
    expect(zonerOn(sim, "127.0.0.1:7911").forElement(q("#cliff-btn"), "button")).toBe("cliff_button");
  });

  it("markers: task_start, progress and task_end fire on the new ports exactly as on the old", () => {
    const m = (host: string, page: string, cfg: ZoneConfig) => {
      load(page);
      const z = zonerOn(cfg, host);
      return z.markersFor(z.forNav(document), document);
    };
    expect(m("127.0.0.1:7911", "a-step1-v1", sim)).toEqual({ start: { idle_s: 120 }, progress: [] });
    expect(m("127.0.0.1:7912", "b-result-v1", sim)).toEqual({ progress: ["result_read"] });
    expect(m("127.0.0.1:7911", "a-notedraft-v2", sim)).toEqual({ progress: ["note_field"], end: { reason: "note_saved" } });
    expect(m("127.0.0.1:7801", "a-step1-v1", sim)).toBeUndefined();            // the old port is simply not a sandbox site here
  });

  it("rect protocol: a zone request resolves on the new port and is a miss on an unconfigured host", () => {
    load("a-result-v1");
    const btn = q("#cliff-btn");
    btn.getBoundingClientRect = () => ({ left: 10, top: 20, right: 150, bottom: 52, width: 140, height: 32, x: 10, y: 20, toJSON() {} }) as DOMRect;
    Object.assign(window, { innerWidth: 1200, innerHeight: 800, outerWidth: 1200, outerHeight: 880, screenX: 0, screenY: 0, scrollX: 0, scrollY: 0, devicePixelRatio: 2 });
    const want = { request_id: "z", frame_id: "top", zone: "cliff_button" };
    const hit = resolveRect(window, want, { salt: SALT, matcher, zoner: zonerOn(sim, "127.0.0.1:7911") });
    expect(hit.found).toBe(true);
    expect(hit.rect).toEqual({ x: 10, y: 20, w: 140, h: 32 });
    // an element's own data-understudy-zone attribute still works on any host; a configured selector needs the right host
    const sel = resolveRect(window, want, { salt: SALT, matcher, zoner: zonerOn(sim, "127.0.0.1:7801") });
    expect(sel.found).toBe(true);        // #cliff-btn carries data-understudy-zone="cliff_button" itself
    q("#cliff-btn").removeAttribute("data-understudy-zone");
    expect(resolveRect(window, want, { salt: SALT, matcher, zoner: zonerOn(sim, "127.0.0.1:7801") }).found).toBe(false);
    expect(resolveRect(window, want, { salt: SALT, matcher, zoner: zonerOn(sim, "127.0.0.1:7911") }).found).toBe(true);
  });
});
