import bundled from "../generated/bundled.json";
import { loadConfig, type StorageArea } from "../shared/config";
import { STORAGE_KEYS } from "../shared/types";

const store = chrome.storage.local as unknown as StorageArea;
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const roles = [...new Set((bundled.zones.sites as { pack: string }[]).map((s) => s.pack))];

async function render(): Promise<void> {
  const cfg = await loadConfig(store);
  const status = (await chrome.runtime.sendMessage({ kind: "popup_status" }).catch(() => null)) as
    | { stats: { accepted: number; last_error: string | null }; queued: number; l1_targets: string[]; desktop_reachable: boolean }
    | null;
  const on = $("on") as HTMLInputElement;
  on.checked = cfg.capturing;
  $("state").textContent = cfg.capturing ? "Capture is on" : "Capture is off";
  const sel = $("role") as HTMLSelectElement;
  // Once the engine's onboarding has created the identity, the role is its, not ours to choose.
  $("role-row").hidden = $("role-row-label").hidden = cfg.identity_adopted;
  $("who").textContent = cfg.identity_adopted ? `${cfg.person} (from Understudy)` : `${cfg.person} (local until you onboard)`;
  if (!sel.options.length) for (const r of roles) sel.add(new Option(r, r));
  sel.value = roles.includes(cfg.role) ? cfg.role : roles[0] ?? "";
  $("queued").textContent = String(status?.queued ?? 0);
  $("sent").textContent = String(status?.stats.accepted ?? 0);
  $("l1").textContent = status?.l1_targets.length ? `on (${status.l1_targets.length})` : "off";
  $("desk").textContent = status?.desktop_reachable ? "connected" : "not seen";
  $("err").textContent = status?.stats.last_error ? `Last problem: ${status.stats.last_error}` : "";
}

($("on") as HTMLInputElement).addEventListener("change", async (e) => {
  const cfg = await loadConfig(store);
  await store.set({ [STORAGE_KEYS.config]: { ...cfg, capturing: (e.target as HTMLInputElement).checked } });
  await render();
});
($("role") as HTMLSelectElement).addEventListener("change", async (e) => {
  const cfg = await loadConfig(store);
  await store.set({ [STORAGE_KEYS.config]: { ...cfg, role: (e.target as HTMLSelectElement).value } });
});
void render();
setInterval(() => void render(), 2000);
