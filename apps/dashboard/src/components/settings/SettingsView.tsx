import { useEffect, useState, type ReactNode } from "react";
import { MODES, MODE_LABEL, groupTypes, isMode, learnedLines, modeLine, type Mode } from "../../lib/attention";
import type { AttentionSettings, SkillsAnswer } from "../../types";
import { HELP_LOCKS, PRESETS, STOPS_LINE, THEMES, APP_ONLY, defaultNote, groupModeOf, lockOf, lockPatch, presetOf, sectionOf, settingsHeadline, skillRows, maxBudgetChoices, maxMinutesChoices, usd, wakeLine, withSkill, type DefaultId, type HelpLock, type LiveView, type Preset, type Theme } from "../../screens/Settings/model";
import type { DesktopSettings, WakeStatus } from "../../screens/Settings/bridge";
import { Hint } from "../Hint";
import { ConfirmRow, Details } from "../ui";
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
  /** Set every kind in one group that can change to one mode, in one request. */
  onGroup: (types: string[], mode: Mode) => void;
  /** Put every kind back to the loudness the worker set (what Knack learned can only ever make a kind quieter). */
  onResetLearned: () => void;
  /** The two-second help level glance (an attention setting, so it works without the app). */
  onLevelGlance: (on: boolean) => void;
  /** Hey Knack's switch and status from the app, or null (a browser tab, or a build without the listener). */
  wake: WakeStatus | null;
  onWake: (on: boolean) => void;
  /** Today's counts and the held items that need the worker, with their Why? (inside Per kind). Null while it loads or when the layer is off. */
  today?: ReactNode;
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
  version?: string | null;
  /** The Connections panel (plugins and MCP apps), when that track has built it. Null or absent: no row. */
  connections?: ReactNode;
  /** Every call Knack makes (the call list), shown inside Advanced once it is opened. Absent: Advanced holds only the version line. */
  advanced?: ReactNode;
  /** The skill files on this Mac and which are off, from the tasks service. Null or absent (it did not answer): no row. */
  skills?: SkillsAnswer | null;
  onSkills?: (patch: { use_claude_skills?: boolean; off?: string[]; max_minutes?: number; max_budget_usd?: number }) => void;
}

function Row({ id, title, line, control, error, def }: { id: string; title: string; line?: ReactNode; control: ReactNode; error?: string | null; def?: DefaultId }) {
  return (
    <section className="st-row" id={`set-${id}`} aria-labelledby={`set-${id}-h`}>
      <div className="st-text">
        <h3 className="st-name" id={`set-${id}-h`}>{title}</h3>
        {(line || def) && <p className="st-line" data-testid={`line-${id}`}>{line}{line && def ? " " : ""}{def && <span className="st-default" data-testid={`default-${id}`}>{defaultNote(def)}</span>}</p>}
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
  const asked = sectionOf(p.section);
  const target = asked === "about" || asked === "models" ? "advanced" : asked;      // the old rows live under Advanced now
  const [confirmReset, setConfirmReset] = useState(false);
  const [adv, setAdv] = useState(target === "advanced");
  useEffect(() => {
    if (!target || typeof document === "undefined") return;
    document.getElementById(`set-${target}`)?.scrollIntoView?.({ block: "start" });
  }, [target]);

  const d = p.desktop;
  // An answer with no list of kinds is an answer with none: the words show with nothing pressed, and the groups are empty.
  const attn = p.attention ? { ...p.attention, types: Array.isArray(p.attention.types) ? p.attention.types : [] } : null;
  const preset = attn ? presetOf(attn) : null;
  const lock = lockOf(d);
  const headline = settingsHeadline({ live: p.live.disabled && !p.live.checked && /cannot reach/.test(p.live.line) ? null : p.live.checked, preset });
  const groups = attn ? groupTypes(attn.types) : [];
  const learned = attn ? learnedLines(attn.learned) : [];

  return (
    <div className="st" data-testid="settings">
      {headline && <p className="kc-headline st-headline" data-testid="headline">{headline}</p>}
      <Row id="live-models" title="Use live models" line={p.live.line} def="live-models"
        control={<Switch label="Use live models" checked={p.live.checked} disabled={p.live.disabled} onChange={p.onLive} />} />

      <Row id="interruptions" title="Interruptions" def="interruptions"
        line={STOPS_LINE}
        error={p.attentionError}
        control={attn ? <Segmented<Preset> label="Interruptions" value={preset} options={PRESETS.map((x) => ({ id: x.id, label: x.label }))} onChange={p.onPreset} /> : <span className="u-muted">Loading</span>} />
      {attn && (
        <div className="st-sub">
          {(p.attentionExample || !preset) && <p className="kc-sub" data-testid="line-interruptions-more">{p.attentionExample ? "Example settings: a change here only changes this screen." : ""}{p.attentionExample && !preset ? " " : ""}{!preset ? "Some kinds are set one by one." : ""}</p>}
          <Details summary="More" wide>
            <div className="st-kinds">
              {p.today}
              <div className="st-group" data-testid="groups">
                {groups.map((g) => {
                  const free = g.rows.filter((r) => !r.fixed);
                  const fixed = g.rows.filter((r) => r.fixed);
                  return (
                    <div key={g.id} className="st-kind" data-testid={`group-${g.id}`}>
                      <span className="st-kind__name">{g.title}<Hint label={`About ${g.title}`}>{g.blurb}{fixed.length > 0 ? ` Always shown: ${fixed.map((r) => r.label.toLowerCase()).join(", ")}.` : ""}</Hint></span>
                      {free.length > 0
                        ? <Segmented<Mode> label={`How loud: ${g.title}`} value={groupModeOf(g.rows)} options={MODES.map((m) => ({ id: m, label: MODE_LABEL[m] }))} onChange={(m) => p.onGroup(free.map((r) => r.type), m)} />
                        : <span className="u-muted" data-testid={`fixed-${g.id}`}>Always shown</span>}
                    </div>
                  );
                })}
              </div>
              <Details summary="Each kind" wide>
                <div className="st-kinds">
                  {groups.map((g) => {
                    const fixed = g.rows.filter((r) => r.fixed);
                    const rows = g.rows.filter((r) => !r.fixed);
                    return (
                      <div key={g.id} className="st-group" data-testid={`kinds-${g.id}`}>
                        <p className="kc-label">{g.title}</p>
                        {fixed.length > 0 && <p className="st-kind-note" data-testid={`always-${g.id}`}>Always shown: {fixed.map((r) => r.label.toLowerCase()).join(", ")}.</p>}
                        {rows.map((r) => (
                          <div key={r.type} className="st-kind" data-testid={`notice-${r.type}`}>
                            <span className="st-kind__name">{r.label}<Hint label={`What ${r.label} does at this setting`}>{modeLine(r.cls, r.mode)}</Hint></span>
                            <Segmented<Mode> label={`How loud: ${r.label}`} value={isMode(r.mode) ? r.mode : null} options={MODES.map((m) => ({ id: m, label: MODE_LABEL[m] }))} onChange={(m) => p.onMode(r.type, m)} />
                          </div>
                        ))}
                      </div>
                    );
                  })}
                  {learned.length > 0 && (
                    <div className="st-group" data-testid="learned">
                      <p className="kc-label">What Knack learned</p>
                      <ul className="yd-plain">{learned.map((l) => <li key={l.type}>{l.text}</li>)}</ul>
                      {confirmReset ? (
                        <ul className="kc-list"><ConfirmRow question="Reset what Knack learned?" consequence="Every kind goes back to the loudness you set. Nothing else changes." confirmLabel="Reset it" onConfirm={() => { setConfirmReset(false); p.onResetLearned(); }} onCancel={() => setConfirmReset(false)} /></ul>
                      ) : (
                        <div><button type="button" className="btn btn--secondary btn--sm" onClick={() => setConfirmReset(true)}>Reset what Knack learned</button></div>
                      )}
                    </div>
                  )}
                </div>
              </Details>
            </div>
          </Details>
        </div>
      )}

      <Row id="coaching" title="Coaching" def="coaching"
        line={d ? (d.cueEnabled ? "Knack can offer hints while you work." : "No hints while you work.") : APP_ONLY}
        control={d ? <Switch label="Coaching" checked={!!d.cueEnabled} onChange={(on) => p.onDesktop({ cueEnabled: on })} /> : null} />
      {(d || attn) && (
        <div className="st-sub">
          {d && (
            <div className="st-kind"><span className="st-kind__name" id="set-lock-h">Help level<span className="st-kind__line">{defaultNote("help-level")}</span></span>
              <div className="segmented" role="group" aria-labelledby="set-lock-h">
                {HELP_LOCKS.map((o) => <button key={String(o.id)} type="button" aria-pressed={lock === o.id} onClick={() => { if (lock !== o.id) p.onDesktop(lockPatch(o.id as HelpLock)); }}>{o.label}</button>)}
              </div>
            </div>
          )}
          {attn && (
            <Details summary="More">
              <div className="st-kind"><span className="st-kind__name">Show the help level for two seconds when it changes<span className="st-kind__line">Only when nothing else is on screen and you have been still for a moment.</span></span>
                <Switch label="Show the help level for two seconds when it changes" checked={!!attn.level_glance} onChange={p.onLevelGlance} />
              </div>
            </Details>
          )}
        </div>
      )}

      <Row id="hey-knack" title="Listen for Hey Knack" def="hey-knack" line={p.wake ? wakeLine(p.wake) : APP_ONLY}
        control={p.wake ? <Switch label="Listen for Hey Knack" checked={p.wake.switchOn} onChange={p.onWake} /> : null} />

      <Row id="move-aside" title="Move aside while Knack works" def="move-aside"
        line={d ? (d.minimiseWhileWorking === false ? "The window stays where it is while an agent works." : "The window minimises while an agent works. The pill shows what it is doing.") : APP_ONLY}
        control={d ? <Switch label="Move aside while Knack works" checked={d.minimiseWhileWorking !== false} onChange={(on) => p.onDesktop({ minimiseWhileWorking: on })} /> : null} />

      <Row id="open-at-login" title="Open at login" def="open-at-login"
        line={d ? (d.launchAtLogin ? "Knack opens when you log in. Routines only run while Knack is open." : "Off. Routines only run while Knack is open.") : APP_ONLY}
        control={d ? <Switch label="Open at login" checked={!!d.launchAtLogin} onChange={(on) => p.onDesktop({ launchAtLogin: on })} /> : null} />

      {p.skills && (
        <>
          <Row id="skills" title="Use my skills" def="skills"
            line="Knack can use the skill files already on this Mac."
            control={<Switch label="Use my skills" checked={p.skills.use_claude_skills !== false} onChange={(on) => p.onSkills?.({ use_claude_skills: on })} />} />
          {skillRows(p.skills).length > 0 && (
            <div className="st-sub">
              <Details summary="More" wide>
                <div className="st-kinds" data-testid="skills-list">
                  {skillRows(p.skills).map((k) => (
                    <div key={k.name} className="st-kind">
                      <span className="st-kind__name">{k.name}{k.description && <span className="st-kind__line">{k.description}</span>}</span>
                      <Switch label={`Use the skill ${k.name}`} checked={k.on} disabled={p.skills!.use_claude_skills === false} onChange={(on) => p.onSkills?.({ off: withSkill(p.skills!.off, k.name, on) })} />
                    </div>
                  ))}
                </div>
              </Details>
            </div>
          )}
        </>
      )}

      <Row id="appearance" title="Appearance" control={<Segmented<Theme> label="Appearance" value={p.theme} options={THEMES} onChange={p.onTheme} />} />

      <Row id="views" title="Views"
        control={<Segmented<"worker" | "admin"> label="View as" value={p.view} options={[{ id: "worker", label: "Worker" }, { id: "admin", label: "Admin" }]} onChange={p.onView} />} />
      {p.stories && p.stories.length > 0 && (
        <div className="st-sub">
          <label className="st-kind"><span className="st-kind__name">Example week</span>
            <select className="select" value={p.stories.find((x) => x.selected)?.id ?? ""} onChange={(e) => p.onStory?.(e.target.value)}>
              {p.stories.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </label>
        </div>
      )}

      {p.connections && <section className="st-row st-row--block" id="set-connections" aria-labelledby="set-connections-h"><div className="st-text"><h3 className="st-name" id="set-connections-h">Connections</h3>{p.connections}</div></section>}

      <div className="st-sub" id="set-advanced">
        <Details summary="Advanced" defaultOpen={target === "advanced"} onToggle={setAdv} wide>
          <div className="st-kinds">
            {p.skills && (
              <>
                {typeof p.skills.max_minutes === "number" && (
            <Row id="max-minutes" title="Longest a task runs" def="max-minutes" line="A background task stops by itself after this long."
              control={
                <select className="select" aria-label="Longest a task runs" value={p.skills.max_minutes} onChange={(e) => p.onSkills?.({ max_minutes: Number(e.target.value) })}>
                  {maxMinutesChoices(p.skills.max_minutes).map((n) => <option key={n} value={n}>{n} minutes</option>)}
                </select>
              } />
          )}
          {typeof p.skills.max_budget_usd === "number" && (
            <Row id="max-budget" title="Most a task may spend" def="max-budget" line="A task stops by itself when it reaches this."
              control={
                <select className="select" aria-label="Most a task may spend" value={p.skills.max_budget_usd} onChange={(e) => p.onSkills?.({ max_budget_usd: Number(e.target.value) })}>
                  {maxBudgetChoices(p.skills.max_budget_usd).map((n) => <option key={n} value={n}>{usd(n)}</option>)}
                </select>
              } />
          )}
              </>
            )}
            {adv && p.advanced}
            <p className="kc-sub" data-testid="line-about">Knack{p.version ? ` ${p.version}` : ""}. It runs on this Mac only. <a className="kc-link" href="#/setup">Set up again<span aria-hidden="true"> ›</span></a></p>
          </div>
        </Details>
      </div>
    </div>
  );
}
