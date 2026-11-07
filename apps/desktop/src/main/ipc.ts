import { ipcMain } from 'electron'
import type { IpcMainEvent, IpcMainInvokeEvent } from 'electron'
import { z } from 'zod'
import { IPC } from '../shared/ipc'
import type { InvokeArgs, InvokeChannel, InvokeResult, SendArgs, SendChannel } from '../shared/ipc'
import type { Services } from '../shared/contracts'
import { HELP_LEVEL_LABELS, PersonaIdSchema } from '../shared/protocol'
import type { LiveToolCall, RendererStatePatch } from '../shared/protocol'
import type { ConfirmBroker } from './confirm'
import type { ServiceContext } from './context'
import { mintLiveToken, mintWakeToken } from './live-auth'
import { registerFilesIpc } from './files'
import type { Permissions } from './permissions'
import type { SessionController } from './session'
import type { Dispatch } from './tools/dispatcher'
import type { Windows } from './windows'

export interface IpcDeps {
  ctx: ServiceContext
  services: Services
  windows: Windows
  dispatch: Dispatch
  confirm: ConfirmBroker
  session: SessionController
  permissions?: Permissions
}

const PermissionPaneSchema = z.enum(['screen', 'microphone', 'accessibility'])

const RendererStatePatchSchema = z.object({
  phase: z.enum(['asleep', 'listening_for_name', 'connecting', 'live', 'thinking', 'speaking', 'error']).optional(),
  micMuted: z.boolean().optional(),
  lastError: z.string().max(500).optional(),
})

const DockModeSchema = z.enum(['compact', 'expanded'])

export function registerIpc(deps: IpcDeps): void {
  const { ctx, services, windows, dispatch, confirm, session } = deps

  const guard = (event: IpcMainEvent | IpcMainInvokeEvent) => {
    if (!windows.owns(event.sender.id)) throw new Error('IPC from an unknown sender')
  }
  const handle = <C extends InvokeChannel>(channel: C, fn: (...args: InvokeArgs<C>) => Promise<InvokeResult<C>> | InvokeResult<C>) => {
    ipcMain.handle(channel, (event, ...args) => {
      guard(event)
      return fn(...(args as InvokeArgs<C>))
    })
  }
  const listen = <C extends SendChannel>(channel: C, fn: (...args: SendArgs<C>) => void) => {
    ipcMain.on(channel, (event, ...args) => {
      try {
        guard(event)
        fn(...(args as SendArgs<C>))
      } catch (err) {
        ctx.log('ipc', `${channel} rejected:`, err instanceof Error ? err.message : err)
      }
    })
  }

  handle(IPC.stateGet, () => ctx.state.get())
  handle(IPC.statePatch, (patch) => {
    const parsed = RendererStatePatchSchema.parse(patch) as RendererStatePatch
    ctx.state.patch(parsed)
  })
  handle(IPC.settingsGet, () => ctx.settings.get())
  // FILES: the folder list changes only through the native dialog in main (files:addFolder), never through a renderer patch.
  handle(IPC.settingsPatch, (patch) => {
    if (typeof patch === 'object' && patch !== null && 'fileFolders' in patch) {
      const { fileFolders: _ignored, ...rest } = patch as Record<string, unknown>
      return ctx.settings.patch(rest, { trusted: true })
    }
    return ctx.settings.patch(patch, { trusted: true })
  })
  handle(IPC.liveToken, async (personaId) => {
    PersonaIdSchema.parse(personaId)
    return mintLiveToken()
  })
  handle(IPC.wakeToken, () => mintWakeToken())
  handle(IPC.liveToolCall, (call: LiveToolCall) => dispatch(call.name, call.args, 'live'))
  handle(IPC.teachingSystemInstruction, (personaId) => services.teaching.systemInstruction(PersonaIdSchema.parse(personaId)))
  handle(IPC.captureLiveFrame, () => services.capture.liveFrame())
  handle(IPC.learnerSnapshot, () => services.learner.snapshot())
  handle(IPC.learnerMarkdown, (req) => services.learner.editMarkdown(req))
  // AGENTS hook: agent:cancel
  handle(IPC.agentCancel, (id) => services.agents.cancel(String(id)))
  handle(IPC.dockMode, (mode) => windows.setDockMode(DockModeSchema.parse(mode)))

  listen(IPC.overlayReady, (size) => {
    ctx.log('ipc', `overlay ready ${size.width}x${size.height}`)
    ctx.sendOverlay({ type: 'chip', level: ctx.state.get().level, label: HELP_LEVEL_LABELS[ctx.state.get().level] })
  })
  listen(IPC.wakeDetected, ({ personaId, source }) => {
    PersonaIdSchema.parse(personaId)
    ctx.bus.emit('wake', { personaId, source })
    ctx.bus.emit('session:request', { personaId, source })
  })
  listen(IPC.sessionEnded, (reason) => ctx.bus.emit('session:ended', { reason }))
  listen(IPC.stopPressed, () => session.stop('stop'))
  listen(IPC.liveTranscript, ({ role, text, final }) => {
    ctx.state.addCaption(role, text, final)
    if (ctx.settings.get().captions) services.overlay.caption(role, text, final)
    // TEACH: the runner reacts to worry, "show me again" and "let me try" (the mock runner has no such method).
    if (role === 'user' && final) (services.runner as { noteUtterance?: (t: string) => void }).noteUtterance?.(text)
  })
  listen(IPC.liveStatus, ({ connected, phase }) => {
    if (!connected && phase !== 'error') return
    ctx.state.patch({ phase, ...(phase === 'error' ? {} : { lastError: undefined }) })
  })
  listen(IPC.confirmAnswer, ({ id, choice }) => {
    if (!confirm.answer(id, choice)) ctx.log('ipc', 'ignored confirm answer (stale or invalid)')
  })

  // SHELL: macOS permissions. Subscribers get changes pushed while they are subscribed (main polls only then).
  const { permissions } = deps
  if (permissions) {
    handle(IPC.permissionsStatus, () => permissions.status())
    handle(IPC.permissionsRequestMicrophone, () => permissions.requestMicrophone())
    handle(IPC.permissionsRequestScreen, () => permissions.requestScreen())
    ipcMain.on(IPC.permissionsRequestAccessibility, (event) => {
      try {
        guard(event)
        event.returnValue = permissions.requestAccessibility()
      } catch {
        event.returnValue = false
      }
    })
    listen(IPC.permissionsOpenSettings, (pane) => permissions.openSettings(PermissionPaneSchema.parse(pane)))
    listen(IPC.permissionsRelaunch, () => permissions.relaunch())
    ipcMain.on(IPC.permissionsSubscribe, (event) => {
      try {
        guard(event)
        permissions.subscribe(event.sender)
      } catch (err) {
        ctx.log('ipc', 'permissions subscribe rejected:', err instanceof Error ? err.message : err)
      }
    })
    ipcMain.on(IPC.permissionsUnsubscribe, (event) => permissions.unsubscribe(event.sender))
  }

  // FILES: "Files I can look at" (folder dialog, status, reindex, delete, search).
  if (services.files) registerFilesIpc({ files: services.files, owns: (id) => windows.owns(id), log: ctx.log })
}
