// The wake card page: a title, one short body and equal-weight buttons. Draws only what main sends, as text (never HTML). A click counts as
// "real" only when the browser produced it from a mouse; main checks the sender and the card again before it believes this.
import { isRealMouseClick, type WakeCardView } from '../../main/wake/card-ipc'

const api = window.knackWakeCard
const card = document.getElementById('card') as HTMLElement
const title = document.getElementById('t') as HTMLElement
const body = document.getElementById('b') as HTMLElement
const buttons = document.getElementById('buttons') as HTMLElement
let current: WakeCardView | null = null

function measure(): void {
  requestAnimationFrame(() => {
    const r = card.getBoundingClientRect()
    api?.size({ w: Math.ceil(r.width) + 8, h: Math.ceil(r.height) + 8 })
  })
}

function show(v: WakeCardView): void {
  current = v
  title.textContent = v.title
  body.textContent = v.body
  buttons.replaceChildren(
    ...v.buttons.map((b) => {
      const el = document.createElement('button')
      el.type = 'button'
      el.textContent = b.label
      el.addEventListener('click', (e) => {
        if (!current) return
        api?.answer({ id: current.id, buttonId: b.id, real: isRealMouseClick({ isTrusted: e.isTrusted, detail: e.detail, pointerType: (e as PointerEvent).pointerType, button: e.button }) })
      })
      return el
    }),
  )
  card.hidden = false
  measure()
}

api?.onShow(show)
api?.onHide(() => {
  current = null
  card.hidden = true
})
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && current) api?.esc(current.id)
})
