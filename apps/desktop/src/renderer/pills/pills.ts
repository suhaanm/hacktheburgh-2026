// The background agent pills page: draws the list main sends, as text only (never HTML). One pill per task or run: an icon by the kind of work (animated while it works, a dot while
// it waits for an OK, a check or a mark when it ends), the words, and a stop button on hover for a task that can be stopped. A click on a pill opens Knack on that work.
import type { PillItem, PillsView } from '../../main/knack/agent-pills-model'
import '../../main/knack/agent-pills-ipc'

const api = window.knackPills
const list = document.getElementById('pills') as HTMLUListElement

// A few strokes per kind of work, drawn in the page (no image files: the page may load nothing).
const GLYPH: Record<PillItem['route'], string> = {
  answer: 'M3 5h10M3 8h7M3 11h9', // lines of text
  browser: 'M2.5 8a5.5 5.5 0 1 0 11 0a5.5 5.5 0 1 0 -11 0M2.5 8h11M8 2.5c2 2 2 9 0 11M8 2.5c-2 2 -2 9 0 11', // a globe
  desktop: 'M2.5 3.5h11v7h-11zM6 13h4M8 10.5v2.5', // a screen
  claude_agent: 'M5 4.5l-3 3.5l3 3.5M11 4.5l3 3.5l-3 3.5M9 3l-2 10', // code
  run: 'M4 8h8M8 4v8', // a plain plus: a background run of the service
}
const svg = (d: string): SVGSVGElement => {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  s.setAttribute('viewBox', '0 0 16 16')
  s.setAttribute('width', '14')
  s.setAttribute('height', '14')
  s.setAttribute('aria-hidden', 'true')
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
  p.setAttribute('d', d)
  p.setAttribute('fill', 'none')
  p.setAttribute('stroke', 'currentColor')
  p.setAttribute('stroke-width', '1.4')
  p.setAttribute('stroke-linecap', 'round')
  p.setAttribute('stroke-linejoin', 'round')
  s.append(p)
  return s
}

function icon(item: PillItem): HTMLElement {
  const el = document.createElement('span')
  el.className = 'icon'
  el.dataset.phase = item.phase
  el.dataset.animated = String(item.animated)
  if (item.phase === 'done') el.append(svg('M3.5 8.5l3 3l6 -6.5')) // a quiet check
  else if (item.phase === 'failed') {
    const dot = document.createElement('i') // a red dot: it stays until the pill is clicked
    dot.className = 'faildot'
    el.append(dot)
  } else if (item.phase === 'stopped') el.append(svg('M4 8h8')) // a dash
  else {
    // Running: the work's own glyph inside a ring that breathes (still when motion is reduced); planning or waiting for an OK: the same ring, still (with a dot for the OK).
    const ring = document.createElement('i')
    ring.className = 'ring'
    el.append(ring, svg(GLYPH[item.route]))
    if (item.phase === 'waiting') {
      const dot = document.createElement('i')
      dot.className = 'dot'
      el.append(dot)
    }
  }
  return el
}

const LABEL: Record<PillItem['phase'], string> = { working: 'Working', waiting: 'Needs your OK', done: 'Finished', failed: 'Did not finish', stopped: 'Stopped' }

function pill(item: PillItem): HTMLLIElement {
  const li = document.createElement('li')
  li.className = 'pill'
  li.dataset.phase = item.phase
  li.dataset.leaving = String(item.leaving)
  const open = document.createElement('button')
  open.type = 'button'
  open.className = 'open'
  open.title = item.text
  open.setAttribute('aria-label', `${LABEL[item.phase]}: ${item.text}`)
  const text = document.createElement('span')
  text.className = 'text'
  text.textContent = item.text
  open.append(icon(item), text)
  open.addEventListener('click', () => api?.open(item.id))
  li.append(open)
  if (item.stoppable) {
    const stop = document.createElement('button')
    stop.type = 'button'
    stop.className = 'stop'
    stop.setAttribute('aria-label', `Stop: ${item.text}`)
    stop.title = 'Stop'
    stop.append(svg('M5.5 5.5l5 5M10.5 5.5l-5 5'))
    stop.addEventListener('click', (e) => {
      e.stopPropagation()
      api?.stop(item.id)
    })
    li.append(stop)
  }
  return li
}

let lastJson = ''
function draw(view: PillsView): void {
  const json = JSON.stringify(view)
  if (json === lastJson) return
  lastJson = json
  const kids: HTMLElement[] = view.items.map(pill)
  if (view.more > 0) {
    const more = document.createElement('li')
    more.className = 'pill more'
    more.textContent = `+${view.more}`
    kids.push(more)
  }
  list.replaceChildren(...kids)
  requestAnimationFrame(() => api?.size(Math.ceil(list.getBoundingClientRect().height) + 6))
}

draw({ items: [], more: 0 })
api?.onState(draw)
void api?.get().then(draw).catch(() => undefined)
