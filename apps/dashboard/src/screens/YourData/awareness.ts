// The glance switches belong to the desktop app's awareness module and its consent card (apps/desktop/src/main/awareness-card.ts), reached through
// the main window's preload: window.alongside.awareness.state() and .setConsent(choice). Without it (a browser tab) the switches say so.
// The consent text comes from the app, whole, and is printed as it is.
export interface AwarenessState {
  available: boolean;
  consentText: string;
  consentShort: string;
  agreed: boolean;
  enabled: boolean;
  trigger: boolean;
  periodic: boolean;
  strict: boolean;
  intervalSec: number;
  dailyUsd: number;
  callsToday: number;
  lastSkip: string | null;
}
export interface AwarenessChoice { trigger: boolean; periodic?: boolean; strict?: boolean }
export interface AwarenessBridge {
  state(): Promise<AwarenessState>;
  setConsent(choice: AwarenessChoice): Promise<AwarenessState>;
}

type Win = { alongside?: { awareness?: Partial<AwarenessBridge> } };

export function awarenessBridge(w: Win | undefined = typeof window === "undefined" ? undefined : (window as unknown as Win)): AwarenessBridge | null {
  const a = w?.alongside?.awareness;
  return a && typeof a.state === "function" && typeof a.setConsent === "function" ? (a as AwarenessBridge) : null;
}

/** The choice a switch makes: the periodic look and strict mode ride on the triggered look; withdrawing the triggered look withdraws them all. */
export function choiceFor(cur: Pick<AwarenessState, "trigger" | "periodic" | "strict">, change: Partial<AwarenessChoice>): AwarenessChoice {
  const trigger = change.trigger ?? cur.trigger;
  if (!trigger) return { trigger: false };
  return { trigger: true, periodic: change.periodic ?? cur.periodic, strict: change.strict ?? cur.strict };
}
