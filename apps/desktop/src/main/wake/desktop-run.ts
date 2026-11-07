// The one place the wake feature asks the agent service for a real click, over loopback, after the worker's real mouse click on Allow.
//
//   POST {agent}/desktop/click   header X-Understudy-Token (data/.token), body { point: { x, y }, grid: 1000, card_id, consent: "corner_card_click" }
//   -> { ok: boolean, reason?: string }
//
// The route is a contract for the agent service (see docs/knack-ux/09-wake-voice.md, "What the agent service must provide"): it issues the owner's
// one-time token and RunPermit through the existing owner_present flow for THIS request, brings the target app forward through the countdown,
// runs the click through the full pipeline and the real-actuator guards, and never runs unattended, for a purchase or on a real account. Until
// it exists the call fails closed (`route_missing`) and nothing is clicked. Never throws.
import type { DesktopRunPort } from './controller'

export interface DesktopRunDeps {
  agentUrl: string
  isLoopback: (url: string) => boolean
  readToken: () => string | null
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export function createDesktopRunPort(d: DesktopRunDeps): DesktopRunPort {
  let ctl: AbortController | null = null
  return {
    async run(req) {
      if (!d.isLoopback(d.agentUrl)) return { ok: false, reason: 'not_loopback' }
      const token = d.readToken()
      if (!token) return { ok: false, reason: 'no_token' }
      const [y0, x0, y1, x1] = req.box
      const doFetch = d.fetchImpl ?? ((i, init) => fetch(i, init))
      const my = new AbortController()
      ctl = my
      const timer = setTimeout(() => my.abort(), d.timeoutMs ?? 90_000)
      try {
        const res = await doFetch(`${d.agentUrl.replace(/\/+$/, '')}/desktop/click`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-understudy-token': token },
          body: JSON.stringify({ point: { x: Math.round((x0 + x1) / 2), y: Math.round((y0 + y1) / 2) }, grid: 1000, card_id: req.cardId, consent: 'corner_card_click' }),
          signal: my.signal,
        })
        if (res.status === 404 || res.status === 405) return { ok: false, reason: 'route_missing' }
        if (!res.ok) return { ok: false, reason: 'refused' }
        const body = (await res.json().catch(() => null)) as { ok?: unknown; reason?: unknown } | null
        return body && body.ok === true ? { ok: true } : { ok: false, reason: typeof body?.reason === 'string' ? body.reason.slice(0, 40) : 'failed' }
      } catch {
        return { ok: false, reason: 'unreachable' }
      } finally {
        clearTimeout(timer)
        if (ctl === my) ctl = null
      }
    },
    stop() {
      ctl?.abort()
    },
  }
}
