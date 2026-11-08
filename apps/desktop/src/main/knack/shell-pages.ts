// The one page of our own that the main window shows before the dashboard: a calm "Starting Knack…" while the services come up, and, if they do not, one plain
// sentence and one Try again button. No logs, no progress text, no spinner words. Served from app://knack/__shell/ (app-protocol.ts), so the page's policy
// forbids inline script and style: the script and the stylesheet are separate files.
import type { StackState } from './stack'
import type { ShellAsset } from './app-protocol'
import type { ShellUiState } from '../../shared/knack'

/** What the page says while starting: the brand name and an ellipsis (two words). */
export const startingText = (appName: string): string => `Starting ${appName}…`
/** After thirty seconds the page says it is still going (the first start can take a minute): the same one line, in other words. */
export const slowStartingText = (appName: string): string => `Still starting ${appName}…`
export const SLOW_START_MS = 30_000

/** The page's state from the lifecycle's. 'idle' reads as starting: the window is open before the first look. */
export function uiStateOf(s: StackState, appName: string, notice?: string | null, slow = false): ShellUiState {
  switch (s.phase) {
    case 'ready':
      return { kind: 'ready' }
    case 'failed':
      return { kind: 'error', message: s.message, ...(s.hint ? { hint: s.hint } : {}) }
    default:
      return { kind: 'starting', text: slow ? slowStartingText(appName) : startingText(appName), ...(notice ? { notice } : {}) }
  }
}

const escapeHtml = (s: string): string => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)

const CSS = `:root { color-scheme: light dark; --bg: #f6f7f9; --fg: #141922; --muted: #566074; --line: #c9d1dd; --accent: #0a7c78; }
@media (prefers-color-scheme: dark) { :root { --bg: #0e1319; --fg: #e7ebf1; --muted: #9aa6b8; --line: #283341; --accent: #4fd1c5; } }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
body::before { content: ""; position: fixed; top: 0; left: 0; right: 0; height: 40px; -webkit-app-region: drag; }
.stage { min-height: 100%; display: grid; place-content: center; justify-items: center; gap: 14px; padding: 24px; text-align: center; }
.glyph { width: 72px; height: 72px; color: var(--fg); }
.glyph svg { width: 100%; height: 100%; display: block; }
.glyph svg circle[stroke] { animation: breathe 2.4s ease-in-out infinite; }
[data-kind="error"] .glyph svg circle[stroke] { animation: none; opacity: 0.4; }
@keyframes breathe { 0%, 100% { opacity: 0.35; } 50% { opacity: 0.8; } }
@media (prefers-reduced-motion: reduce) { .glyph svg circle[stroke] { animation: none; opacity: 0.62; } }
#text { margin: 0; font-size: 17px; font-weight: 500; letter-spacing: 0.005em; }
[data-kind="starting"] #text { color: var(--muted); font-weight: 400; }
.hint { margin: 0; max-width: 36ch; color: var(--muted); font-size: 13px; }
button { font: inherit; font-size: 14px; font-weight: 500; padding: 8px 18px; border-radius: 8px; border: 1px solid var(--line); background: transparent; color: var(--fg); cursor: pointer; -webkit-app-region: no-drag; }
button:hover { border-color: var(--accent); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
[hidden] { display: none !important; }
`

const JS = `(() => {
  const api = window.knackShell
  const $ = (id) => document.getElementById(id)
  const render = (s) => {
    $('root').dataset.kind = s.kind
    if (s.kind === 'error') {
      $('text').textContent = s.message
      $('hint').textContent = s.hint || ''
      $('hint').hidden = !s.hint
      $('retry').hidden = false
    } else {
      $('text').textContent = s.kind === 'starting' ? s.text : ''
      $('hint').hidden = true
      $('retry').hidden = true
    }
    $('notice').textContent = s.kind === 'starting' && s.notice ? s.notice : ''
    $('notice').hidden = !(s.kind === 'starting' && s.notice)
  }
  if (api) {
    api.get().then(render).catch(() => {})
    api.onState(render)
    $('retry').addEventListener('click', () => api.retry())
  }
})()
`

export function shellPages(o: { appName: string; glyphSvg: string }): Record<string, ShellAsset> {
  // Inline SVG in HTML needs no namespace attribute (and the page then holds no web address at all).
  const glyph = o.glyphSvg.replace(/<!--[\s\S]*?-->/g, '').replace(/\swidth="\d+"|\sheight="\d+"|\sxmlns="[^"]*"/g, '')
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${escapeHtml(o.appName)}</title>
<link rel="stylesheet" href="/__shell/starting.css">
</head>
<body>
<main id="root" class="stage" data-kind="starting">
<div class="glyph" aria-hidden="true">${glyph}</div>
<p id="text" role="status" aria-live="polite">${escapeHtml(startingText(o.appName))}</p>
<p id="notice" class="hint" hidden></p>
<p id="hint" class="hint" hidden></p>
<button id="retry" type="button" hidden>Try again</button>
</main>
<script src="/__shell/starting.js"></script>
</body>
</html>
`
  return {
    'starting.html': { type: 'text/html; charset=utf-8', body: html },
    'starting.css': { type: 'text/css; charset=utf-8', body: CSS },
    'starting.js': { type: 'text/javascript; charset=utf-8', body: JS },
  }
}
