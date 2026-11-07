// Dev-only control surface on 127.0.0.1 so every agent can drive and inspect the app without voice.
import http from 'node:http'
import { AnnotationSchema, PersonaIdSchema } from '../shared/protocol'
import type { OverlayCommand, ShotPurpose } from '../shared/protocol'
import type { Services } from '../shared/contracts'
import type { ServiceContext } from './context'
import type { SessionController } from './session'
import type { ShellTray } from './tray'
import type { Dispatch } from './tools/dispatcher'
import { z } from 'zod'
import { getStageTruthSource, type ElectronStageSource } from './showtime/stage-truth'

export interface DebugDeps {
  ctx: ServiceContext
  services: Services
  dispatch: Dispatch
  session: SessionController
  // Optional window capture helpers (Electron only); absent in unit tests.
  capture?: { overlayPng(): Promise<Buffer | null>; dockPng(): Promise<Buffer | null>; hudPng?(): Promise<Buffer | null> }
  // Understudy: kill switch, HUD and model port inspection (dev only, like the rest of this surface).
  understudy?: {
    kill: Pick<import('./kill-switch').KillSwitch, 'trigger' | 'clear' | 'state'>
    hud?: Pick<import('./hud-model').HudModel, 'state' | 'setProposal' | 'setQueuePending'>
  }
  // SHELL: the menu-bar item (absent when headless).
  tray?: Pick<ShellTray, 'info' | 'activate' | 'primaryClick'>
}

const MAX_BODY = 1_000_000

const OverlayCmdSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('show'), annotations: z.array(AnnotationSchema) }),
  z.object({ type: z.literal('clear'), ids: z.array(z.string()).optional() }),
  z.object({ type: z.literal('caption'), speaker: z.enum(['user', 'assistant', 'system']), text: z.string(), final: z.boolean() }),
  z.object({ type: z.literal('chip'), level: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]), label: z.string() }),
])

function readJson(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => {
      size += chunk.length
      if (size > MAX_BODY) {
        reject(new Error('body too large'))
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8')
      if (!text) return resolve({})
      try {
        resolve(JSON.parse(text))
      } catch {
        reject(new Error('invalid JSON'))
      }
    })
    req.on('error', reject)
  })
}

export function startDebugServer(deps: DebugDeps): http.Server {
  const { ctx, services, dispatch, session } = deps
  const port = Number(process.env.ALONGSIDE_DEBUG_PORT || 7777)

  const server = http.createServer(async (req, res) => {
    const send = (status: number, body: unknown) => {
      res.writeHead(status, { 'content-type': 'application/json' })
      res.end(JSON.stringify(body))
    }
    try {
      // Block browsers (CSRF) and DNS-rebinding: only plain local clients, no Origin header.
      const host = req.headers.host ?? ''
      if (req.headers.origin || !/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host)) return send(403, { error: 'forbidden' })

      const url = new URL(req.url ?? '/', `http://${host}`)
      const route = `${req.method} ${url.pathname}`

      switch (route) {
        case 'GET /health':
          return send(200, { ok: true, pid: process.pid, mock: process.env.ALONGSIDE_MOCK === '1', phase: ctx.state.get().phase })
        case 'GET /state':
          return send(200, ctx.state.get())
        case 'POST /tool': {
          const body = z.object({ name: z.string(), args: z.unknown().optional() }).parse(await readJson(req))
          return send(200, await dispatch(body.name, body.args ?? {}, 'debug'))
        }
        case 'POST /inject': {
          const body = z.object({ text: z.string(), interrupt: z.boolean().optional() }).parse(await readJson(req))
          services.live.inject(body.text, { interrupt: body.interrupt })
          return send(200, { ok: true })
        }
        case 'POST /overlay': {
          const body = z.object({ cmd: OverlayCmdSchema }).parse(await readJson(req))
          ctx.sendOverlay(body.cmd as OverlayCommand)
          return send(200, { ok: true })
        }
        case 'GET /shot': {
          const purpose = z.enum(['live', 'ground', 'verify']).catch('ground').parse(url.searchParams.get('purpose') ?? 'ground') as ShotPurpose
          const shot = await services.capture.grab(purpose)
          res.writeHead(200, { 'content-type': 'image/jpeg', 'x-shot-width': String(shot.widthPx), 'x-shot-height': String(shot.heightPx) })
          return res.end(Buffer.from(shot.jpegBase64, 'base64'))
        }
        case 'POST /wake': {
          const body = z.object({ personaId: PersonaIdSchema }).parse(await readJson(req))
          ctx.bus.emit('wake', { personaId: body.personaId, source: 'button' })
          ctx.bus.emit('session:request', { personaId: body.personaId, source: 'button' })
          return send(200, { ok: true })
        }
        case 'POST /stop':
          session.stop('stop')
          return send(200, { ok: true })
        case 'POST /settings': {
          const body = z.object({ patch: z.record(z.string(), z.unknown()) }).parse(await readJson(req))
          // FILES: folders are added only through the native dialog (files:addFolder), never via a settings patch.
          const { fileFolders: _folders, ...patch } = body.patch
          return send(200, ctx.settings.patch(patch))
        }
        case 'GET /tray':
          return deps.tray ? send(200, deps.tray.info()) : send(404, { error: 'no tray (headless)' })
        case 'POST /tray/click': {
          if (!deps.tray) return send(404, { error: 'no tray (headless)' })
          const body = z.object({ id: z.string().optional() }).parse(await readJson(req))
          if (body.id === undefined) deps.tray.primaryClick() // the icon click itself
          else if (!deps.tray.activate(body.id)) return send(400, { error: `unknown or disabled menu item: ${body.id}` })
          return send(200, { ok: true })
        }
        // Interactive-demo rehearsal: a real input click on the practice desktop (no Accessibility), and its page state.
        case 'POST /stage/click': {
          const stage = getStageTruthSource() as ElectronStageSource | null
          if (!stage?.debugClick) return send(404, { error: 'no practice desktop (ALONGSIDE_DEMO_DIRECTOR=1 and the interactive demo)' })
          const body = z.object({ id: z.string() }).parse(await readJson(req))
          return send(200, await stage.debugClick(body.id))
        }
        case 'GET /stage/state': {
          const stage = getStageTruthSource()
          if (!stage) return send(404, { error: 'no practice desktop' })
          return send(200, await stage.snapshot())
        }
        case 'POST /kill': {
          if (!deps.understudy) return send(404, { error: 'no kill switch' })
          return send(200, await deps.understudy.kill.trigger('cli'))
        }
        case 'POST /kill/clear': {
          if (!deps.understudy) return send(404, { error: 'no kill switch' })
          await deps.understudy.kill.clear()
          return send(200, deps.understudy.kill.state())
        }
        case 'GET /hud': {
          if (!deps.understudy?.hud) return send(404, { error: 'no HUD' })
          return send(200, deps.understudy.hud.state())
        }
        case 'POST /hud/proposal': {
          if (!deps.understudy?.hud) return send(404, { error: 'no HUD' })
          const body = z
            .object({
              proposal: z
                .object({ id: z.string(), title: z.string(), what: z.string(), howOften: z.string(), hoursSaved: z.tuple([z.number(), z.number()]).nullable(), touches: z.array(z.string()), never: z.array(z.string()) })
                .nullable(),
            })
            .parse(await readJson(req))
          deps.understudy.hud.setProposal(body.proposal)
          return send(200, deps.understudy.hud.state())
        }
        case 'GET /model': {
          const { lastBootReport } = await import('./model-port')
          return send(200, { provider: ctx.modelPort?.provider ?? null, models: ctx.modelPort?.models() ?? null, boot: lastBootReport() })
        }
        case 'GET /overlay.png':
        case 'GET /hud.png':
        case 'GET /dock.png': {
          const png = await (route === 'GET /overlay.png' ? deps.capture?.overlayPng() : route === 'GET /hud.png' ? deps.capture?.hudPng?.() : deps.capture?.dockPng())
          if (!png) return send(404, { error: 'window not available' })
          res.writeHead(200, { 'content-type': 'image/png' })
          return res.end(png)
        }
        default:
          return send(404, { error: 'not found' })
      }
    } catch (err) {
      send(400, { error: err instanceof Error ? err.message : String(err) })
    }
  })

  server.listen(port, '127.0.0.1', () => ctx.log('debug', `listening on 127.0.0.1:${port}`))
  server.on('error', (err) => ctx.log('debug', 'server error:', err.message))
  return server
}
