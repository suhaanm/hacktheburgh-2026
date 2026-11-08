// The last choice a worker made on an insight screen (which view, which comparison, whose week), kept on this device only and read back the next time,
// so the screen opens the way they left it. docs/knack-ux/defaults.md lists every default and every remembered choice.
//
// Rules that keep this safe:
//  - It stores a short word from a fixed list, never text the worker typed, never an id of a person (the person's own id is already on this device).
//  - A value that is not in the list is ignored, so an old or edited value can never put a screen in a state it cannot draw.
//  - Storage can be blocked (private window, site data cleared): every read and write is caught and the screen simply uses its default.
//  - It never stores a consent. Whether something may run by itself is a setting the worker switches on in the open; remembering a tab is not consent.
import { useCallback, useState } from "react";

/** The storage keys keep the product's old name on purpose: they are internal identifiers, not copy (docs/knack-ux/banned-phrases.json). */
export const REMEMBER_PREFIX = "understudy-last-";

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const browserStorage = (): KeyValueStorage | null => {
  try { return typeof window !== "undefined" ? window.localStorage : null; } catch { return null; }
};

/** The remembered word if it is one of `allowed`, else `fallback`. Pure over its storage, so it is tested without a browser. */
export function readRemembered<T extends string>(name: string, allowed: readonly T[], fallback: T, storage: KeyValueStorage | null = browserStorage()): T {
  try {
    const v = storage?.getItem(REMEMBER_PREFIX + name) ?? null;
    return v !== null && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
  } catch { return fallback; }
}

/** Remember `value`; the default removes the key, so a screen that is back to its default leaves nothing behind. Returns whether it was stored. */
export function writeRemembered<T extends string>(name: string, value: T, fallback: T, storage: KeyValueStorage | null = browserStorage()): boolean {
  try {
    if (!storage) return false;
    if (value === fallback) storage.removeItem(REMEMBER_PREFIX + name); else storage.setItem(REMEMBER_PREFIX + name, value);
    return true;
  } catch { return false; }
}

/** A piece of state that starts from the last choice and writes each new one back. */
export function useRemembered<T extends string>(name: string, allowed: readonly T[], fallback: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => readRemembered(name, allowed, fallback));
  const set = useCallback((next: T) => { setValue(next); writeRemembered(name, next, fallback); }, [name, fallback]);
  return [value, set];
}

/** The same for a free choice the screen can verify itself (a person or a week that must be in a list the engine just sent): the caller checks it. */
export function readRememberedFree(name: string, storage: KeyValueStorage | null = browserStorage()): string | null {
  try {
    const v = storage?.getItem(REMEMBER_PREFIX + name) ?? null;
    return v !== null && v.length > 0 && v.length <= 64 && /^[\w .:@-]+$/.test(v) ? v : null;
  } catch { return null; }
}
export function writeRememberedFree(name: string, value: string | null, storage: KeyValueStorage | null = browserStorage()): boolean {
  try {
    if (!storage) return false;
    if (!value) storage.removeItem(REMEMBER_PREFIX + name); else if (value.length <= 64 && /^[\w .:@-]+$/.test(value)) storage.setItem(REMEMBER_PREFIX + name, value); else return false;
    return true;
  } catch { return false; }
}
