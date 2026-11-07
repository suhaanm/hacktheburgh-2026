// Grounding for point_at over HTTP: POST {agent}/cue/ground with one frame and a closed menu, answered in the shape {available, chosen,
// box_2d, confidence, source, model_tier, latency_ms}. The route (the MODELS track) writes the image ledger row and applies its own gate;
// this adapter checks the gates FIRST and sends the same four booleans in the body, so a frame never leaves when the gate is closed.
// Browser pages are grounded from the DOM before this is tried (the composite below), which needs no frame at all.
import type { FrameProvider } from './session'
import type { GateVerdict } from './gates'
import type { GroundAnswer, GroundPort, GroundRequest } from './ports'

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** Parses an answer from the grounding route; anything off-shape is null (never trusted, never partially used). */
export function parseGroundAnswer(json: unknown): GroundAnswer | null {
  const body = isObj(json) && isObj(json.data) ? json.data : json
  if (!isObj(body)) return null
  const avail = Array.isArray(body.available) ? body.available.filter((x): x is string => typeof x === 'string').slice(0, 8) : []
  const chosen = typeof body.chosen === 'string' ? body.chosen : null
  const conf = typeof body.confidence === 'number' && Number.isFinite(body.confidence) ? Math.min(1, Math.max(0, body.confidence)) : 0
  const box = Array.isArray(body.box_2d) && body.box_2d.length === 4 && body.box_2d.every((n) => typeof n === 'number' && Number.isFinite(n)) ? (body.box_2d as [number, number, number, number]) : null
  const source = body.source === 'dom' ? 'dom' : 'vision'
  return { available: avail, chosen, box_2d: box, confidence: conf, source, ...(body.model_tier === 'lite' || body.model_tier === 'full' ? { model_tier: body.model_tier } : {}), ...(typeof body.latency_ms === 'number' ? { latency_ms: body.latency_ms } : {}) }
}

export interface HttpGroundOptions {
  agentUrl: string
  isLoopback: (url: string) => boolean
  frames: FrameProvider
  gates: () => Promise<GateVerdict>
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export function createHttpGroundPort(o: HttpGroundOptions): GroundPort {
  if (!o.isLoopback(o.agentUrl)) throw new Error('the grounding service must be on this machine (127.0.0.1)')
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  return {
    async ground(req: GroundRequest) {
      const verdict = await o.gates()
      if (!verdict.open) return null
      const frame = await o.frames.grab()
      if (!frame) return null
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 8000)
      try {
        const body = JSON.stringify({
          frame: { mime: 'image/jpeg', b64: frame.jpeg.toString('base64'), width: frame.width, height: frame.height },
          menu: req.menu.slice(0, 6).map((m) => ({ id: m.id, label: m.label })),
          ...(req.app_kind ? { app_kind: req.app_kind } : {}),
          purpose: 'cue.ground',
          gates: verdict.gate,
        })
        const res = await doFetch(`${o.agentUrl.replace(/\/+$/, '')}/cue/ground`, { method: 'POST', headers: { 'content-type': 'application/json' }, body, signal: ctl.signal })
        if (!res.ok) return null
        return parseGroundAnswer(await res.json())
      } catch {
        return null
      } finally {
        clearTimeout(timer)
        frame.release()
      }
    },
  }
}

/** DOM first (a browser page, exact and free), then the vision route. Either may be missing. */
export function createCompositeGround(dom: GroundPort | null, vision: GroundPort | null): GroundPort | null {
  if (!dom && !vision) return null
  return {
    async ground(req) {
      if (dom) {
        const a = await dom.ground(req).catch(() => null)
        if (a && a.chosen && a.box_2d) return a
      }
      return vision ? vision.ground(req) : null
    },
  }
}
