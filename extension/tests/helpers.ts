import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const repo = resolve(here, "..", "..");
export const schemaDir = join(repo, "packages", "schema");

export function loadSchema(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(join(schemaDir, name), "utf8"));
}

export function ajvFor(name: string) {
  const Ctor = ((Ajv2020 as unknown as { default?: unknown }).default ?? Ajv2020) as unknown as new (o: object) => import("ajv").default;
  const ajv = new Ctor({ strict: false, allErrors: true });
  (addFormats as unknown as (a: unknown) => void)(ajv);
  return ajv.compile(loadSchema(name));
}

export const validateAgainstEventSchema = ajvFor("event.schema.json");

import { SensitiveMatcher, type SensitiveSpec } from "../src/shared/sensitive";
import bundled from "../src/generated/bundled.json";
import { Zoner, pickSite, type ZoneConfig } from "../src/shared/zones";
import type { CaptureRecord } from "../src/shared/types";

export const SALT = "0123456789abcdef0123456789abcdef";
export const matcher = new SensitiveMatcher(bundled.sensitive as SensitiveSpec[]);
export const zoneConfig = bundled.zones as ZoneConfig;

export function zonerFor(host: string, role = "benefits-processor"): Zoner {
  return new Zoner(zoneConfig, pickSite(zoneConfig, host, [role]));
}

/** Install a document into the current jsdom window and return a recorder for capture output. */
export function setPage(html: string): void {
  document.documentElement.innerHTML = `<head></head><body>${html}</body>`;
}

export function recorder() {
  const records: CaptureRecord[] = [];
  return { records, emit: (r: CaptureRecord) => void records.push(r) };
}

export function fire<T extends Event>(el: EventTarget, ev: T): T {
  el.dispatchEvent(ev);
  return ev;
}
