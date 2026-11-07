// Showtime's own practice-desktop window: fullscreen on the primary display, loading apps/demo-stage/index.html from
// disk (no server), driven with executeJavaScript for the stage API and sendInputEvent for clicks (no Accessibility
// permission needed). It sits below the dock and the overlay. Ground-truth boxes come from the stage's own
// __stage.rects, so the annotations land exactly on the real elements.
import path from 'node:path'
import { app, BrowserWindow, screen } from 'electron'
import type { NormBox } from '../../shared/protocol'

export interface StageWindow {
  go(route: string): Promise<void>
  rects(): Promise<Record<string, NormBox>>
  phraseBoxes(target: string, phrase: string): Promise<NormBox[]>
  // The visible text of a stage element (by data-ground-id); '' when it is not on screen.
  messageText(target: string): Promise<string>
  click(target: string): Promise<boolean>
  deliverScam(): Promise<void>
  hide(): void
  show(): void
  size(): { width: number; height: number; displayWidth: number; displayHeight: number } | null
  capture(): Promise<Buffer | null>
  close(): void
  isOpen(): boolean
}

// The demo cursor: our own page, so injecting a visual pointer is fine. The real click is a synthetic input event.
const CURSOR_JS = `(function(){
  if (document.getElementById('st-cursor')) return;
  var c = document.createElement('div');
  c.id = 'st-cursor';
  c.setAttribute('aria-hidden', 'true');
  c.style.cssText = 'position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483646;pointer-events:none;opacity:0;transform:translate(-100px,-100px);transition:transform 600ms cubic-bezier(.3,.7,.2,1),opacity 200ms;will-change:transform';
  c.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M4 2l15 9-6.5 1.6L9.6 19z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg><span id="st-ripple" style="position:absolute;left:-10px;top:-10px;width:22px;height:22px;border-radius:50%;border:3px solid #2a4f8f;opacity:0;transition:opacity 250ms,transform 250ms"></span>';
  document.body.appendChild(c);
})()`

const clamp = (n: number): number => Math.min(1000, Math.max(0, n))

export async function openStageWindow(opts: { log: (msg: string) => void; indexHtml?: string; exitButton?: boolean; seedScam?: boolean }): Promise<StageWindow> {
  const display = screen.getPrimaryDisplay()
  const win = new BrowserWindow({
    x: display.bounds.x,
    y: display.bounds.y,
    width: display.bounds.width,
    height: display.bounds.height,
    show: false,
    frame: false,
    resizable: false,
    movable: false,
    fullscreenable: false,
    skipTaskbar: true,
    backgroundColor: '#e9eef5',
    title: 'Practice desktop',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  })
  win.setMenuBarVisibility(false)
  // The practice desktop never opens windows or leaves the bundled page (local file navigation, such as its own pages, is allowed).
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('file:')) event.preventDefault()
  })
  // Below the dock ('floating') and the overlay ('screen-saver'), above ordinary windows.
  win.setAlwaysOnTop(true, 'floating', -1)
  const index = opts.indexHtml ?? path.join(app.getAppPath(), 'apps/demo-stage/index.html')
  await win.loadFile(index, { query: { still: '1', ...(opts.exitButton ? { exit: '1' } : {}), ...(opts.seedScam ? { seedscam: '1' } : {}) }, hash: 'desktop' })
  win.showInactive()
  if (process.platform === 'darwin') win.setSimpleFullScreen(true)
  else win.setBounds(display.bounds)

  const js = <T>(code: string): Promise<T> => win.webContents.executeJavaScript(code, true) as Promise<T>
  const alive = (): boolean => !win.isDestroyed() && !win.webContents.isDestroyed()

  // The stage defines window.__stage synchronously at load; wait for `ready` anyway.
  for (let i = 0; i < 50; i++) {
    if (await js<boolean>('Boolean(window.__stage && window.__stage.ready)').catch(() => false)) break
    await new Promise((r) => setTimeout(r, 100))
  }
  await js(CURSOR_JS).catch(() => undefined)
  const dims = await js<{ w: number; h: number; sw: number; sh: number }>('({w:innerWidth,h:innerHeight,sw:screen.width,sh:screen.height})').catch(() => null)
  if (dims && (dims.w !== dims.sw || dims.h < dims.sh - 1)) opts.log(`stage window is ${dims.w}x${dims.h} but the display is ${dims.sw}x${dims.sh}: boxes use the screen-space mapping`)

  const quote = (s: string): string => JSON.stringify(s)

  // The stage must stay shown, on top and fullscreen for the whole tour (a real-Mac run lost it ~40 s in). Only the
  // tour's own hide() (while a real browser is shown) may take it away; anything else is put right within a second.
  let wantVisible = true
  const assertOnScreen = (): void => {
    if (!alive()) return
    if (!win.isVisible()) win.showInactive()
    win.setAlwaysOnTop(true, 'floating', -1)
    if (process.platform === 'darwin') {
      win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true })
      if (!win.isSimpleFullScreen()) win.setSimpleFullScreen(true)
    } else if (win.isMinimized()) win.restore()
    win.moveTop()
  }
  assertOnScreen()
  const keepAlive = setInterval(() => {
    if (!alive()) return clearInterval(keepAlive)
    if (!wantVisible) return
    const level = !win.isVisible() || (process.platform === 'darwin' && !win.isSimpleFullScreen()) || win.isMinimized()
    if (level) {
      opts.log('stage window was hidden or resized by the system: putting it back')
      assertOnScreen()
    } else {
      win.setAlwaysOnTop(true, 'floating', -1)
      win.moveTop()
    }
  }, 1000)
  win.on('closed', () => clearInterval(keepAlive))

  return {
    async go(route) {
      if (!alive()) return
      await js(`__stage.go(${quote(route)}); (function(){var c=document.getElementById('st-cursor'); if(c){c.style.opacity='0'}})()`)
    },
    async rects() {
      if (!alive()) return {}
      return js<Record<string, NormBox>>("__stage.rects({space:'screen'})").catch(() => ({}))
    },
    async phraseBoxes(target, phrase) {
      if (!alive()) return []
      // Viewport-normalised text-range boxes; the window covers the display, so this equals screen space.
      const boxes = await js<NormBox[]>(`(function(id, phrase){
        var el = document.querySelector('[data-ground-id="' + id + '"]');
        if (!el) return [];
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var W = innerWidth, H = innerHeight, out = [];
        while (walker.nextNode()) {
          var n = walker.currentNode, i = n.nodeValue.indexOf(phrase);
          if (i < 0) continue;
          var r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + phrase.length);
          Array.prototype.forEach.call(r.getClientRects(), function(b){ if (b.width > 1) out.push({ xmin: b.left / W * 1000, ymin: b.top / H * 1000, xmax: b.right / W * 1000, ymax: b.bottom / H * 1000 }); });
          break;
        }
        return out;
      })(${quote(target)}, ${quote(phrase)})`).catch(() => [])
      return boxes.map((b) => ({ xmin: clamp(b.xmin), ymin: clamp(b.ymin), xmax: clamp(b.xmax), ymax: clamp(b.ymax) }))
    },
    async messageText(target) {
      if (!alive()) return ''
      return js<string>(`(function(id){
        var el = document.querySelector('[data-ground-id="' + id + '"]');
        return el ? String(el.innerText || el.textContent || '').trim() : '';
      })(${quote(target)})`).catch(() => '')
    },
    async click(target) {
      if (!alive()) return false
      const pt = await js<{ x: number; y: number } | null>(`(function(id){
        var r = __stage.rectOf(id); if (!r) return null;
        return { x: (r.xmin + r.xmax) / 2 / 1000 * innerWidth, y: (r.ymin + r.ymax) / 2 / 1000 * innerHeight };
      })(${quote(target)})`).catch(() => null)
      if (!pt) {
        opts.log(`stage.click: ${target} is not visible`)
        return false
      }
      await js(`(function(x, y){ var c = document.getElementById('st-cursor'); if (!c) return; c.style.opacity = '1'; c.style.transform = 'translate(' + x + 'px,' + y + 'px)'; })(${pt.x}, ${pt.y})`)
      await new Promise((r) => setTimeout(r, 650))
      const before = await js<number>('__stage.events().length').catch(() => 0)
      const x = Math.round(pt.x)
      const y = Math.round(pt.y)
      win.webContents.sendInputEvent({ type: 'mouseMove', x, y })
      win.webContents.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 })
      await js(`(function(){ var r = document.getElementById('st-ripple'); if (r) { r.style.opacity = '1'; r.style.transform = 'scale(1.8)'; setTimeout(function(){ r.style.opacity = '0'; r.style.transform = 'scale(1)'; }, 280); } })()`).catch(() => undefined)
      await new Promise((r) => setTimeout(r, 90))
      win.webContents.sendInputEvent({ type: 'mouseUp', x, y, button: 'left', clickCount: 1 })
      await new Promise((r) => setTimeout(r, 160))
      // If the synthetic press did not register, click the element itself (still the real stage handler).
      const after = await js<number>('__stage.events().length').catch(() => before)
      if (after === before) {
        opts.log(`stage.click: ${target} did not react to the synthetic input, using element.click()`)
        await js(`(function(id){ var e = document.querySelector('[data-ground-id="' + id + '"]'); if (e) e.click(); })(${quote(target)})`).catch(() => undefined)
      }
      return true
    },
    async deliverScam() {
      if (alive()) await js("__stage.deliverScam('bank')").catch(() => undefined)
    },
    hide() {
      wantVisible = false
      if (alive()) win.hide()
    },
    show() {
      wantVisible = true
      if (alive()) {
        assertOnScreen()
        app.focus({ steal: true }) // a real browser the tour opened may be frontmost: take the screen back
      }
    },
    size() {
      if (!alive()) return null
      const b = win.getContentBounds()
      return { width: b.width, height: b.height, displayWidth: display.bounds.width, displayHeight: display.bounds.height }
    },
    async capture() {
      if (!alive()) return null
      return (await win.webContents.capturePage()).toPNG()
    },
    close() {
      wantVisible = false
      clearInterval(keepAlive)
      if (!alive()) return
      try {
        if (process.platform === 'darwin') win.setSimpleFullScreen(false)
      } catch {
        // already closing
      }
      win.destroy()
    },
    isOpen: alive,
  }
}
