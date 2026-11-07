import { useEffect, type ReactNode } from "react";
import { MODES, MODE_LABEL, groupTypes, modeLine, type Mode } from "../../lib/attention";
import type { AttentionSettings } from "../../types";
import { HELP_LOCKS, PRESETS, STOPS_LINE, THEMES, APP_ONLY, lockOf, lockPatch, presetOf, sectionOf, type HelpLock, type LiveView, type Preset, type Theme } from "../../screens/Settings/model";
import type { DesktopSettings } from "../../screens/Settings/bridge";
import { Hint } from "../Hint";
import { Details } from "../ui";
import "../kc.css";
import "./settings.css";

export interface SettingsViewProps {
  section?: string | null;
  live: LiveView;
  onLive: (on: boolean) => void;
  attention: AttentionSettings | null;
  /** The interruption settings are example settings: say so, once. */
  attentionExample: boolean;
  attentionError: string | null;
  onPreset: (p: Preset) => void;
  onMode: (type: string, mode: Mode) => void;
  /** The desktop app's own settings, or null in a browser tab. */
  desktop: DesktopSettings | null;
  onDesktop: (patch: Partial<DesktopSettings>) => void;
  theme: Theme;
  onTheme: (t: Theme) => void;
  view: "worker" | "admin";
  onView: (v: "worker" | "admin") => void;
  /** Example weeks, only while the data is example data. */
  stories?: { id: string; label: string; selected: boolean }[];
  onStory?: (id: string) => void;
  pinned: boolean;
  onPinned: (on: boolean) => void;
  version?: string | null;
}

function Row({ id, title, line, control, error }: { id: string; title: string; line?: ReactNode; control: ReactNode; error?: string | null }) {
  return (
    <section className="st-row" id={`set-${id}`} aria-labelledby={`set-${id}-h`}>
      <div className="st-text">
        <h3 className="st-name" id={`set-${id}-h`}>{title}</h3>
        {line && <p className="st-line" data-testid={`line-${id}`}>{line}</p>}
        {error && <p className="kc-error" role="alert">{error}</p>}
      </div>
      <div className="st-control">{control}</div>
    </section>
  );
}

function Switch({ label, checked, disabled, onChange }: { label: string; checked: boolean; disabled?: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="toggle st-switch">
      <input type="checkbox" role="switch" aria-label={label} checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden="true" />
    </label>
  );
}

function Segmented<T extends string | number>({ label, value, options, onChange, disabled }: { label: string; value: T | null; options: { id: T; label: string }[]; onChange: (v: T) => void; disabled?: boolean }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => <button key={String(o.id)} type="button" aria-pressed={value === o.id} disabled={disabled} onClick={() => { if (value !== o.id) onChange(o.id); }}>{o.label}</button>)}
    </div>
  );
}

/**
 * The contents of Settings: one row per setting, in the spec's order, one printed line under each that needs one. A row that depends on the
 * desktop app says "Available in the Knack app." in a browser tab instead of vanishing. "Use live models" is first and says why when it is disabled.
 */
export function SettingsView(p: SettingsViewProps) {
  const target = sectionOf(p.section);
  useEffect(() => {
    if (!target || typeof document === "undefined") return;
    document.getElementById(`set-${target}`)?.scrollIntoView?.({ block: "start" });
  }, [target]);

  const d = p.desktop;
  const preset = p.attention ? presetOf(p.attention) : null;
  const lock = lockOf(d);
  const groups = p.attention ? groupTypes(p.attention.types) : [];

  return (
    <div className="st" data-testid="settings">
      <Row id="live-models" title="Use live models" line={p.live.line}
        control={<Switch label="Use live models" checked={p.live.checked} disabled={p.live.disabled} onChange={p.onLive} />} />

      <Row id="interruptions" title="Interruptions"
        line={<>{STOPS_LINE}{p.attentionExample && <> Example settings: a change here only changes this screen.</>}{p.attention && !preset ? " Some kinds are set one by one." : ""}</>}
        error={p.attentionError}
        control={p.attention ? <Segmented<Preset> label="Interruptions" value={preset} options={PRESETS.map((x) => ({ id: x.id, label: x.label }))} onChange={p.onPreset} /> : <span className="u-muted">Loading</span>} />
      {p.attention && (
        <div className="st-sub">
          <Details summary="Per kind" wide>
            <div className="st-kinds">
              {groups.map((g) => {
                const fixed = g.rows.filter((r) => r.fixed);
                const rows = g.rows.filter((r) => !r.fixed);
                return (
                  <div key={g.id} className="st-group" data-testid={`group-${g.id}`}>
                    <p className="kc-label">{g.title}</p>
                    {fixed.length > 0 && <p className="st-kind-note" data-testid={`fixed-${g.id}`}>Always shown: {fixed.map((r) => r.label.toLowerCase()).join(", ")}.</p>}
                    {rows.map((r) => (
                      <div key={r.type} className="st-kind" data-testid={`notice-${r.type}`}>
                        <span className="st-kind__name">{r.label}<Hint label={`What ${r.label} does at this setting`}>{modeLine(r.cls, r.mode)}</Hint></span>
                        <div className="segmented" role="group" aria-label={`How loud: ${r.label}`}>
                          {MODES.map((m) => <button key={m} type="button" aria-pressed={r.mode === m} onClick={() => { if (r.mode !== m) p.onMode(r.type, m); }}>{MODE_LABEL[m]}</button>)}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </Details>
        </div>
      )}

      <Row id="coaching" title="Coaching"
        line={d ? (d.cueEnabled ? "Knack can offer hints while you work." : "No hints while you work.") : APP_ONLY}
        control={d ? <Switch label="Coaching" checked={!!d.cueEnabled} onChange={(on) => p.onDesktop({ cueEnabled: on })} /> : null} />
      {d && (
        <div className="st-sub">
          <div className="st-kind"><span className="st-kind__name" id="set-lock-h">Help level</span>
            <div className="segmented" role="group" aria-labelledby="set-lock-h">
              {HELP_LOCKS.map((o) => <button key={String(o.id)} type="button" aria-pressed={lock === o.id} onClick={() => { if (lock !== o.id) p.onDesktop(lockPatch(o.id as HelpLock)); }}>{o.label}</button>)}
            </div>
          </div>
        </div>
      )}

      <Row id="move-aside" title="Move aside while Knack works"
        line={d ? (d.minimiseWhileWorking === false ? "The window stays where it is while an agent works." : "The window minimises while an agent works. The pill shows what it is doing.") : APP_ONLY}
        control={d ? <Switch label="Move aside while Knack works" checked={d.minimiseWhileWorking !== false} onChange={(on) => p.onDesktop({ minimiseWhileWorking: on })} /> : null} />

      <Row id="open-at-login" title="Open at login"
        line={d ? (d.launchAtLogin ? "Knack opens when you log in. Routines only run while Knack is open." : "Off. Routines only run while Knack is open.") : APP_ONLY}
        control={d ? <Switch label="Open at login" checked={!!d.launchAtLogin} onChange={(on) => p.onDesktop({ launchAtLogin: on })} /> : null} />

      <Row id="appearance" title="Appearance" control={<Segmented<Theme> label="Appearance" value={p.theme} options={THEMES} onChange={p.onTheme} />} />

      <Row id="models" title="Models and cost" control={<a className="kc-link" href="#/models">Open<span aria-hidden="true"> ›</span></a>} />

      <Row id="views" title="Views"
        control={<Segmented<"worker" | "admin"> label="View as" value={p.view} options={[{ id: "worker", label: "Worker" }, { id: "admin", label: "Admin" }]} onChange={p.onView} />} />
      {p.stories && p.stories.length > 0 && (
        <div className="st-sub">
          <label className="st-kind"><span className="st-kind__name">Example week</span>
            <select className="select" value={p.stories.find((s) => s.selected)?.id ?? ""} onChange={(e) => p.onStory?.(e.target.value)}>
              {p.stories.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </label>
        </div>
      )}
      <div className="st-sub">
        <label className="st-kind"><span className="st-kind__name">Pinned views<span className="st-kind__line">Show Genome, Graph and Presence in the sidebar.</span></span>
          <Switch label="Pinned views" checked={p.pinned} onChange={p.onPinned} />
        </label>
      </div>

      <Row id="about" title="About"
        line={<>Knack{p.version ? ` ${p.version}` : ""}. Engine 127.0.0.1:7700, agent 127.0.0.1:7710: this Mac only.</>}
        control={<a className="kc-link" href="#/setup">Set up again<span aria-hidden="true"> ›</span></a>} />
    </div>
  );
}
