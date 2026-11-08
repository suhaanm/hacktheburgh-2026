// A stand-in for the Knack desktop app's bridges, for pictures and measurements in a browser: it sets html[data-knack-shell] and gives the page a fake
// window.knackShell (Hey Knack, models, permissions, the sample ring) and window.alongside.awareness. Nothing real is touched: no microphone, no screen, no click.
// Use it as a Playwright init script:  await page.addInitScript(fakeApp, { microphone: "granted", speech: "not-determined", screen: "denied" });
// The function is self-contained (it is serialised into the page), so it must not reference anything outside itself.
export const fakeApp = (perm) => {
  const flag = () => { document.documentElement.dataset.knackShell = "mac-inset"; };
  if (document.documentElement) flag(); else document.addEventListener("DOMContentLoaded", flag);
  const wake = { switchOn: true, listening: true, line: "" };
  const perms = { ...perm };
  window.__rings = 0;
  window.knackShell = {
    platform: "darwin",
    wake: { state: async () => ({ ...wake }), set: async (on) => { wake.switchOn = on; wake.listening = on; return { ...wake }; }, context: async () => true },
    models: { get: async () => ({ useLiveModels: true, keyPresent: false, live: false, running: false }), setUseLiveModels: async () => ({ ok: true }) },
    permissions: { state: async () => ({ ...perms }), request: async (k) => { perms[k] = "granted"; return "granted"; }, openSettings: () => undefined },
    tryRing: async () => { window.__rings++; return { ok: true }; },
  };
  const aw = {
    available: true,
    consentText: "Knack can take a quick look at your screen when you seem stuck. Each look sends one small, reduced picture of your screen to a cloud vision model, which tells it what kind of app you are in. The picture leaves this Mac for that one call, is held in memory only, and is never saved. Every call is listed in Your data.",
    consentShort: "Look at my screen when I seem stuck. Nothing is saved. See every call in Privacy.",
    agreed: false, enabled: false, trigger: false, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0, callsToday: 0, lastSkip: null,
  };
  window.alongside = { awareness: { state: async () => ({ ...aw }), setConsent: async (c) => { aw.trigger = !!c.trigger; aw.agreed = !!c.trigger; return { ...aw }; } } };
};
