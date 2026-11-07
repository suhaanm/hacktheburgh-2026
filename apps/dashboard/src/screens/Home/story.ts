// Which example week Home shows while the engine cannot answer. It moved off Home into Settings, Views ("Example week", shown only with example
// data); the setting calls setExampleWeek and Home reads it. The address form `#/home?story=good` still works and wins. Remembered on this device.
import { useSyncExternalStore } from "react";
import { parseStory, type WorkerStory } from "./data";

export const EXAMPLE_WEEK_KEY = "understudy-example-week";

function read(): WorkerStory {
  try { return parseStory(window.localStorage.getItem(EXAMPLE_WEEK_KEY)); } catch { return "pointers"; }
}

let current: WorkerStory = typeof window === "undefined" ? "pointers" : read();
const listeners = new Set<() => void>();

export const getExampleWeek = (): WorkerStory => current;

export function setExampleWeek(next: WorkerStory): void {
  const v = parseStory(next);
  if (v === current) return;
  current = v;
  try { if (v === "pointers") window.localStorage.removeItem(EXAMPLE_WEEK_KEY); else window.localStorage.setItem(EXAMPLE_WEEK_KEY, v); } catch { /* storage can be blocked */ }
  listeners.forEach((l) => l());
}

export function useExampleWeek(): WorkerStory {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => current, () => "pointers" as WorkerStory);
}
