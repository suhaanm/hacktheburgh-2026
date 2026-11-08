// The Ask bar page: one input. Return sends the line to main (which says whether it went anywhere); Escape closes; main closes it on blur. It draws only text it is given
// (never HTML), and the one sentence under the input is whatever main answered when the line could not be taken.
import '../../main/knack/ask-ipc'

const api = window.knackAsk
const card = document.getElementById('card') as HTMLFormElement
const input = document.getElementById('input') as HTMLInputElement
const reply = document.getElementById('reply') as HTMLElement
const hint = card.querySelector('.hint') as HTMLElement

let busy = false

/** The card's height decides the window's: ask main to fit it. */
function fit(): void {
  requestAnimationFrame(() => api?.size(Math.ceil(card.getBoundingClientRect().height)))
}

function say(line: string | null): void {
  reply.textContent = line ?? ''
  reply.hidden = line === null
  fit()
}

function syncHint(): void {
  hint.dataset.visible = input.value.trim().length > 0 ? 'true' : 'false'
}

api?.onOpen((o) => {
  busy = false
  input.value = o.prefill
  say(null)
  syncHint()
  if (!o.closed) {
    input.focus()
    input.setSelectionRange(input.value.length, input.value.length)
  }
})

input.addEventListener('input', () => {
  if (!reply.hidden) say(null) // typing again takes the old answer away
  syncHint()
})

card.addEventListener('submit', (e) => {
  e.preventDefault()
  const text = input.value.trim()
  if (busy || text.length === 0 || !api) return
  busy = true
  api
    .submit(text)
    .then((r) => {
      busy = false
      if (!r.ok && r.line) say(r.line)
    })
    .catch(() => {
      busy = false
      say('Something went wrong. Try again.')
    })
})

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    e.preventDefault()
    api?.close()
  }
})

syncHint()
fit()
