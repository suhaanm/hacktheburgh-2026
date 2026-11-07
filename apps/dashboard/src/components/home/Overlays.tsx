import { useEffect, useMemo } from "react";
import { useAppState } from "../../store";
import type { WireOverview, WireWorker } from "../firm/wire";
import { CommandPalette, type PaletteLoaders } from "./CommandPalette";
import { navigate } from "../../router";
import { openSettings, toggleAbout, togglePalette } from "./overlayStore";
import { shellKeyAction } from "../shell/keys";
import { SettingsSheet } from "../shell/SettingsSheet";
import { getViewRole } from "./viewAs";
import { GuidedTour } from "./GuidedTour";

/**
 * Where the insight rows come from, found without a hard import: `import.meta.glob` lists the files that exist and loads one only when asked.
 * A missing file means an empty list, so a screen that has not landed yet costs the palette nothing (no build error, no type error).
 * Both loaders are the screens' own (fixtures when the engine is off), so the palette never calls the network by itself.
 */
const HOME_DATA = import.meta.glob("../../screens/Home/data.ts");
const FIRM_DATA = import.meta.glob("../../screens/Firm/data.ts");

interface HomeData { loadWorker?: (person: string | null, story?: "pointers" | "quiet") => Promise<{ data: WireWorker }> }
interface FirmData { loadOverview?: () => Promise<{ data: WireOverview }> }

const load = async <T,>(files: Record<string, () => Promise<unknown>>): Promise<T | null> => {
  const first = Object.values(files)[0];
  if (!first) return null;
  try { return (await first()) as T; } catch { return null; }
};

function defaultLoaders(person: string | null): PaletteLoaders {
  return {
    worker: async () => { const m = await load<HomeData>(HOME_DATA); try { return (await m?.loadWorker?.(person))?.data ?? null; } catch { return null; } },
    overview: async () => { const m = await load<FirmData>(FIRM_DATA); try { return (await m?.loadOverview?.())?.data ?? null; } catch { return null; } },
  };
}

/** True for the Mac and iPad, where the shortcut is Command+K; elsewhere it is Control+K. */
export const isApple = (): boolean => typeof navigator !== "undefined" && /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent);
/** The shortcut as it should be written on a button: "Cmd K" or "Ctrl K". */
export const shortcutLabel = (): string => (isApple() ? "Cmd K" : "Ctrl K");

/**
 * The two overlays, mounted once in the shell: the command palette (Cmd+K or Ctrl+K from anywhere) and the guided tour (never automatic).
 * Props: `loaders` is optional and only for tests or a different source; by default the palette reads the Home and Firm screens' own loaders.
 * Open them from anywhere with `openPalette()` and `startTour()` in overlayStore.
 */
export function Overlays({ loaders }: { loaders?: PaletteLoaders }) {
  const person = useAppState().person;
  const real = useMemo(() => loaders ?? defaultLoaders(person), [loaders, person]);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      // Cmd-1 to Cmd-5, Cmd-comma and Cmd-slash. (Shift-Cmd-K, Stop, is handled by the stop control.) No key ever approves anything.
      const a = shellKeyAction(e, getViewRole());
      if (a?.type === "go") { e.preventDefault(); navigate(a.path); return; }
      if (a?.type === "settings") { e.preventDefault(); openSettings(); return; }
      if (a?.type === "about") { e.preventDefault(); toggleAbout(); return; }
      if (e.key.toLowerCase() !== "k" || e.altKey || e.shiftKey || !(e.metaKey || e.ctrlKey)) return;
      e.preventDefault(); // the browser's own Ctrl+K (search) is not wanted here
      togglePalette();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  return (
    <>
      <CommandPalette loaders={real} />
      <GuidedTour />
      <SettingsSheet />
    </>
  );
}
