// The shell's keyboard map, pure (docs/KNACK_UX.md section 9): Cmd-1 to Cmd-5 go to the five destinations, Cmd-comma opens Settings,
// Cmd-slash opens "About this screen", Shift-Cmd-K stops everything (inside Knack; the global key is the desktop's). Control stands in for
// Command off the Mac. NO KEYSTROKE EVER APPROVES anything: nothing here reaches a queue item, and a test says so.
import { groupOf } from "../home/navModel";
import type { ViewRole } from "../home/viewAs";

export interface KeyLike { key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }
export type ShellAction = { type: "go"; path: string } | { type: "settings" } | { type: "about" } | { type: "stop" };

export function shellKeyAction(e: KeyLike, view: ViewRole): ShellAction | null {
  if (!(e.metaKey || e.ctrlKey) || e.altKey) return null;
  const k = e.key.toLowerCase();
  if (e.shiftKey) return k === "k" ? { type: "stop" } : null;
  if (k === ",") return { type: "settings" };
  if (k === "/") return { type: "about" };
  if (/^[1-5]$/.test(k)) {
    const entry = groupOf(view, "primary")[Number(k) - 1];
    return entry ? { type: "go", path: `/${entry.id}` } : null;
  }
  return null;
}

/** The shortcut written for a button, "⌘1" on a Mac and "Ctrl 1" elsewhere. */
export const chord = (key: string, apple: boolean): string => (apple ? `⌘${key}` : `Ctrl ${key}`);

/** Is the key event aimed at a text field? Shortcuts that are plain letters would not fire there; Cmd chords still do, except Cmd-slash inside a field is left to the field. */
export const inTextField = (t: EventTarget | null): boolean => {
  const el = t as { tagName?: string; isContentEditable?: boolean } | null;
  if (!el?.tagName) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable === true;
};
