// A stand-in for the practice benefits calculator: the page Cue draws over in the storyboard. Our own markup (synthetic, no real service),
// laid out like the sandbox calculators so the ring lands on things that look like what the worker is stuck on. Each element Cue may
// point at carries data-cue-target=<step id>, so the storyboard can measure where the ring and the card must go.
import type { ReactElement } from 'react'

export const STANDIN_CSS = `
.si{position:absolute;inset:0;background:var(--si-bg);color:var(--si-fg);font:400 14px/1.4 'Source Sans 3',system-ui,sans-serif;overflow:hidden}
.si *{box-sizing:border-box}
.si-menubar{position:absolute;left:0;right:0;top:0;height:24px;display:flex;align-items:center;gap:18px;padding:0 14px;background:var(--si-bar);color:var(--si-fg);font:500 12.5px/1 'Source Sans 3',system-ui,sans-serif;border-bottom:1px solid var(--si-line)}
.si-menubar b{font-weight:600}
.si-dock{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);height:56px;width:min(420px,70%);border-radius:16px;background:var(--si-bar);border:1px solid var(--si-line);display:flex;align-items:center;justify-content:center;gap:12px}
.si-dock i{display:block;width:38px;height:38px;border-radius:9px;background:var(--si-line)}
.si-page{position:absolute;left:0;right:0;top:24px;bottom:76px;overflow:hidden}
.si-top{height:52px;display:flex;align-items:center;gap:16px;padding:0 120px;background:var(--si-panel);border-bottom:1px solid var(--si-line)}
.si-top strong{font:600 17px/1 'Source Sans 3',system-ui,sans-serif;letter-spacing:-0.01em}
.si-top span{color:var(--si-muted);font-size:13px}
.si-main{display:grid;grid-template-columns:320px 480px 340px;gap:30px;padding:46px 120px 0}
.si-card{background:var(--si-panel);border:1px solid var(--si-line);border-radius:6px;padding:18px 20px}
.si-card h2{margin:0 0 14px;font:600 14px/1.2 'Source Sans 3',system-ui,sans-serif;color:var(--si-fg)}
.si-rec dl{margin:0;display:grid;grid-template-columns:1fr auto;gap:9px 12px}
.si-rec dt{color:var(--si-muted)}
.si-rec dd{margin:0;font-weight:500;font-variant-numeric:tabular-nums}
.si-field{display:grid;grid-template-columns:130px 1fr;align-items:center;gap:10px;margin-bottom:10px}
.si-field label{color:var(--si-muted)}
.si-input{height:32px;border:1px solid var(--si-control);border-radius:4px;background:var(--si-input);padding:0 10px;display:flex;align-items:center;font-variant-numeric:tabular-nums}
.si-btn{display:inline-flex;align-items:center;justify-content:center;height:42px;min-width:132px;padding:0 20px;border-radius:4px;background:var(--si-primary);color:var(--si-on-primary);font:600 14px/1 'Source Sans 3',system-ui,sans-serif;margin-top:8px}
.si-result{margin-top:20px;padding-top:16px;border-top:1px solid var(--si-line);color:var(--si-muted)}
.si-result strong{display:block;margin-top:2px;font:600 24px/1.1 'Source Sans 3',system-ui,sans-serif;color:var(--si-fg);font-variant-numeric:tabular-nums}
.si-link{display:inline-block;margin-top:12px;padding:3px 0;color:var(--si-link);text-decoration:underline;text-underline-offset:3px;font-weight:500}
.si-area{height:210px;border:1px solid var(--si-control);border-radius:4px;background:var(--si-input);padding:10px;color:var(--si-muted)}
.si-save{display:inline-flex;align-items:center;height:32px;padding:0 14px;margin-top:12px;border:1px solid var(--si-control);border-radius:4px;font-weight:500}
@media (max-width: 900px){
  .si-top{padding:0 16px}
  .si-main{grid-template-columns:1fr;gap:14px;padding:16px 16px 0}
  .si-card{padding:14px 16px}
  .si-field{grid-template-columns:110px 1fr;margin-bottom:8px}
  .si-area{height:90px}
  .si-btn{height:40px}
  .si-dock{width:80%}
}
`

export function StandIn({ dark }: { dark: boolean }): ReactElement {
  const vars = dark
    ? { '--si-bg': '#0a0e13', '--si-panel': '#12181f', '--si-bar': '#161d26', '--si-fg': '#e7ebf1', '--si-muted': '#9aa6b8', '--si-line': '#283341', '--si-control': '#6c7a90', '--si-input': '#0e1319', '--si-primary': '#2a4f9c', '--si-on-primary': '#ffffff', '--si-link': '#8bb4ff' }
    : { '--si-bg': '#e9edf2', '--si-panel': '#ffffff', '--si-bar': '#f6f7f9', '--si-fg': '#141922', '--si-muted': '#566074', '--si-line': '#d8dee8', '--si-control': '#7d889b', '--si-input': '#ffffff', '--si-primary': '#1f4fa8', '--si-on-primary': '#ffffff', '--si-link': '#1f4fa8' }
  return (
    <div className="si" style={vars as React.CSSProperties}>
      <style>{STANDIN_CSS}</style>
      <div className="si-menubar">
        <b>Practice browser</b>
        <span>File</span>
        <span>Edit</span>
        <span>View</span>
        <span>Window</span>
      </div>
      <div className="si-page">
        <div className="si-top">
          <strong>Benefit check</strong>
          <span>Practice case 4417 (synthetic) · Calculator A</span>
        </div>
        <div className="si-main">
          <section className="si-card si-rec" data-cue-target="read_case" aria-label="Household record">
            <h2>Household record</h2>
            <dl>
              <dt>Adults</dt>
              <dd>2</dd>
              <dt>Children</dt>
              <dd>2</dd>
              <dt>Monthly income</dt>
              <dd>£1,640</dd>
              <dt>Monthly rent</dt>
              <dd>£720</dd>
              <dt>Council tax band</dt>
              <dd>C</dd>
              <dt>Postcode area</dt>
              <dd>EH8</dd>
            </dl>
          </section>
          <section className="si-card" aria-label="Calculator A">
            <h2>Calculator A</h2>
            <div className="si-field">
              <label>Adults</label>
              <div className="si-input">2</div>
            </div>
            <div className="si-field">
              <label>Children</label>
              <div className="si-input">2</div>
            </div>
            <div className="si-field">
              <label>Monthly income (£)</label>
              <div className="si-input">1640</div>
            </div>
            <div className="si-field">
              <label>Monthly rent (£)</label>
              <div className="si-input">720</div>
            </div>
            <span className="si-btn" data-cue-target="calc_a">
              Calculate
            </span>
            <div className="si-result">
              Estimated award
              <strong>£412.60 a month</strong>
              <span className="si-link" data-cue-target="cliff_a">
                Check cliff edges
              </span>
            </div>
          </section>
          <section className="si-card" aria-label="Case note">
            <h2>Case note</h2>
            <div className="si-area" data-cue-target="write_note">
              Calculator A, household 4417 …
            </div>
            <span className="si-save">Save note</span>
          </section>
        </div>
      </div>
      <div className="si-dock" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
    </div>
  )
}
