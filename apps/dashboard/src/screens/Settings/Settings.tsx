import { Suspense, lazy, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { ApiError, api, forgetBackoff } from "../../api";
import { SettingsView } from "../../components/settings/SettingsView";
import { setViewRole, useViewRole } from "../../components/home/viewAs";
import { runActive } from "../../lib/agents";
import { withMode, type Mode } from "../../lib/attention";
import { useLoad } from "../../hooks";
import { setState, useAppState } from "../../store";
import type { AttentionPatch, AttentionSettings, Health } from "../../types";
import { useTheme } from "../../components/shell/theme";
import { usePinnedViews } from "../../components/shell/pinned";
import { STORY_LABEL, WORKER_STORIES, parseStory } from "../Home/data";
import { setExampleWeek, useExampleWeek } from "../Home/story";
import { desktopBridge, liveModelsBridge, type DesktopSettings } from "./bridge";
import { liveModels, presetPatch, type Preset } from "./model";

type HealthExt = Health & { key_present?: boolean };

/** The Connections panel is another track's: it is shown only when its file exists, and never blocks Settings. */
const CONNECTIONS = import.meta.glob("../../components/connections/ConnectionsPanel.tsx");
const ConnectionsPanel = Object.values(CONNECTIONS)[0] ? lazy(Object.values(CONNECTIONS)[0] as () => Promise<{ default: ComponentType }>) : null;

/** Ask the engine again, every 2 s, until it says it is live (or mock) as asked, or 60 s pass. The restart takes about 20 s. */
async function waitForMode(wantLive: boolean): Promise<boolean> {
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => window.setTimeout(r, 2000));
    forgetBackoff();
    try {
      const h = await api.health();
      if (h.source === "live" && h.data.mock === !wantLive) return true;
    } catch { /* still restarting */ }
  }
  return false;
}

/**
 * The contents of Settings. The shell owns the frame (a sheet, opened by openSettings(section)); this draws the rows and, with the desktop app's bridge,
 * changes the app's own settings. Without the bridge (a browser tab) a row that needs the app says so and the rest work.
 */
export default function Settings({ section }: { section?: string }) {
  const me = useAppState().person ?? undefined;
  const health = useLoad(() => api.health(), []);
  const runs = useLoad(() => api.agentsRuns(me), [me]);
  const attn = useLoad(() => api.attentionSettings(me), [me]);
  const bridge = useMemo(() => desktopBridge(), []);
  const liveBridge = useMemo(() => liveModelsBridge(), []);
  const [keyPresent, setKeyPresent] = useState<boolean | undefined>(undefined);
  const [desktop, setDesktop] = useState<DesktopSettings | null>(null);
  const [changing, setChanging] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [attention, setAttention] = useState<AttentionSettings | null>(null);
  const [attentionError, setAttentionError] = useState<string | null>(null);
  const [theme, setTheme] = useTheme();
  const view = useViewRole();
  const [pinned, setPinned] = usePinnedViews();
  const seq = useRef(0);
  const story = useExampleWeek();

  useEffect(() => { if (attn.data) setAttention(attn.data); }, [attn.data]);
  useEffect(() => { bridge?.getSettings().then(setDesktop, () => setDesktop(null)); }, [bridge]);
  useEffect(() => { liveBridge?.get().then((m) => setKeyPresent(typeof m.keyPresent === "boolean" ? m.keyPresent : undefined), () => undefined); }, [liveBridge]);

  const h = health.data as HealthExt | null;
  // Only an answer from the engine itself counts: the built-in sample says nothing about the real engine, so then it is "cannot reach".
  const answered = health.status !== "loading" && health.source === "live" ? { ...h, key_present: h?.key_present ?? keyPresent } : null;
  const live = liveModels({ health: answered, canSwitch: !!(liveBridge ?? bridge), running: !!runs.data?.some(runActive), changing });
  const liveView = liveError ? { ...live, line: `${live.line} ${liveError}` } : live;

  const onLive = async (on: boolean) => {
    if (!liveBridge && !bridge) return;
    setLiveError(null); setChanging(true);
    try {
      if (liveBridge) await liveBridge.setUseLiveModels(on); else await bridge!.patchSettings({ useLiveModels: on });
      const ok = await waitForMode(on);
      if (!ok) setLiveError("The engine did not come back in the other mode yet. Nothing else was changed.");
      health.reload();
      void api.health().then((r) => setState({ mock: r.data?.mock ?? null }), () => undefined);
    } catch (e) { setLiveError(e instanceof Error ? `${e.message} Nothing was changed.` : "That did not go through. Nothing was changed."); }
    finally { setChanging(false); }
  };

  /** Apply at once, send it, and put it back with the engine's own words if it is refused. */
  const apply = async (patch: AttentionPatch, optimistic: (x: AttentionSettings) => AttentionSettings) => {
    if (!attention) return;
    const before = attention;
    const mine = ++seq.current;
    setAttention(optimistic(attention)); setAttentionError(null);
    try {
      const r = await api.attentionSet(patch, me);
      if (mine === seq.current && r.data && Array.isArray(r.data.types)) setAttention(r.data);
    } catch (e) {
      if (mine === seq.current) setAttention(before);
      setAttentionError(e instanceof ApiError ? `${e.message}${e.code ? ` (${e.code})` : ""} Nothing changed.` : "That did not go through. Nothing changed.");
    }
  };
  const onPreset = (p: Preset) => {
    if (!attention) return;
    const patch = presetPatch(p, attention);
    void apply(patch, (x) => ({ ...x, budget_per_day: patch.budget_per_day, modes: p === "balanced" ? {} : { ...x.modes, ...patch.modes }, types: x.types.map((t) => (t.fixed ? t : { ...t, mode: patch.modes[t.type] ?? t.mode })) }));
  };
  const onMode = (type: string, mode: Mode) => void apply({ modes: { [type]: mode } }, (x) => withMode(x, type, mode));
  const onResetLearned = () => void apply({ reset_learned: true }, (x) => ({ ...x, learned: {} }));
  const onLevelGlance = (on: boolean) => void apply({ level_glance: on }, (x) => ({ ...x, level_glance: on }));
  const onDesktop = (patch: Partial<DesktopSettings>) => {
    if (!bridge) return;
    const before = desktop;
    setDesktop((d) => ({ ...(d ?? {}), ...patch }));
    bridge.patchSettings(patch).then((r) => { if (r && typeof r === "object") setDesktop(r as DesktopSettings); }, () => setDesktop(before));
  };

  const example = health.source === "demo" || health.data?.mock === true;
  const stories = example ? WORKER_STORIES.map((id) => ({ id, label: STORY_LABEL[id], selected: story === id })) : undefined;
  const onStory = (id: string) => setExampleWeek(parseStory(id));

  return (
    <SettingsView section={section} live={liveView} onLive={(on) => void onLive(on)}
      attention={attention} attentionExample={!!attn.why} attentionError={attentionError} onPreset={onPreset} onMode={onMode} onResetLearned={onResetLearned} onLevelGlance={onLevelGlance}
      desktop={bridge ? desktop : null} onDesktop={onDesktop}
      theme={theme} onTheme={setTheme}
      view={view} onView={setViewRole}
      stories={stories} onStory={onStory}
      pinned={pinned} onPinned={setPinned}
      version={h?.version ?? null}
      connections={ConnectionsPanel ? <Suspense fallback={null}><ConnectionsPanel /></Suspense> : null} />
  );
}
