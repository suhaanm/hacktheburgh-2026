// The single source of IPC channel names plus typed payload maps. No ad-hoc channel strings anywhere else.
import type {
  CompanionState,
  ConfirmRequest,
  LearnerSnapshot,
  LiveFrame,
  LiveInject,
  LiveStatus,
  LiveToken,
  LiveToolCall,
  LiveTranscript,
  MarkdownEditRequest,
  MarkdownEditResult,
  OverlayCommand,
  PersonaId,
  RendererStatePatch,
  SessionEndReason,
  SessionRequest,
  SessionSource,
} from './protocol'
import type { AddFolderResult, FilesSearchResult, FilesStatus } from './files'
import type { PermissionPane, PermissionStatus } from './permissions'
import type { Settings, SettingsPatch } from './settings'
import type { ShellCommand } from './shell'
import type { ShowtimeApi, ShowtimeCue, ShowtimeStartOptions, ShowtimeState } from './showtime'

export const IPC = {
  // state + settings
  stateGet: 'state:get', // invoke
  stateUpdate: 'state:update', // main -> dock+overlay
  statePatch: 'state:patch', // invoke (renderer may patch phase/micMuted/lastError only)
  settingsGet: 'settings:get', // invoke
  settingsPatch: 'settings:patch', // invoke
  // overlay
  overlayCmd: 'overlay:cmd', // main -> overlay
  overlayReady: 'overlay:ready', // overlay -> main
  // sessions (wake/hotkey/button -> Live)
  wakeDetected: 'wake:detected', // dock renderer (spotter/button) -> main
  sessionStart: 'session:start', // main -> dock (open the Live session)
  sessionStop: 'session:stop', // main -> dock (close the Live session now)
  sessionEnded: 'session:ended', // dock -> main (Live closed, with reason)
  stopPressed: 'stop:pressed', // dock Stop button -> main
  // live
  liveToken: 'live:token', // invoke
  wakeToken: 'wake:token', // invoke (ephemeral token constrained to the transcribe model, for the wake spotter)
  liveToolCall: 'live:toolCall', // invoke (dispatcher)
  liveInject: 'live:inject', // main -> dock
  liveTranscript: 'live:transcript', // dock -> main
  liveStatus: 'live:status', // dock -> main
  teachingSystemInstruction: 'teaching:systemInstruction', // invoke
  captureLiveFrame: 'capture:liveFrame', // invoke
  // user decisions and data
  confirmAnswer: 'confirm:answer', // dock -> main (real click only)
  learnerSnapshot: 'learner:snapshot', // invoke
  learnerMarkdown: 'learner:markdown', // invoke
  agentCancel: 'agent:cancel', // invoke
  dockMode: 'dock:mode', // invoke
  // DEMO: Showtime walkthrough
  showtimeStart: 'showtime:start', // invoke
  showtimeStop: 'showtime:stop', // invoke
  showtimeNext: 'showtime:next', // invoke
  showtimePrev: 'showtime:prev', // invoke
  showtimePause: 'showtime:pause', // invoke
  showtimeState: 'showtime:state', // invoke
  showtimeUpdate: 'showtime:update', // main -> dock+overlay
  showtimeCue: 'showtime:cue', // main -> dock (narration audio, view cues)
  // SHELL: macOS permissions + menu bar
  permissionsStatus: 'permissions:status', // invoke
  permissionsRequestMicrophone: 'permissions:requestMicrophone', // invoke
  permissionsRequestScreen: 'permissions:requestScreen', // invoke (runs a capture probe, which makes macOS show its prompt)
  permissionsRequestAccessibility: 'permissions:requestAccessibility', // sendSync (returns boolean, opens the system prompt)
  permissionsOpenSettings: 'permissions:openSettings', // send
  permissionsRelaunch: 'permissions:relaunch', // send
  permissionsSubscribe: 'permissions:subscribe', // send (main polls only while someone is subscribed)
  permissionsUnsubscribe: 'permissions:unsubscribe', // send
  permissionsChanged: 'permissions:changed', // main -> subscriber
  shellCommand: 'shell:command', // main (tray) -> dock
  // FILES: "Files I can look at". addFolder opens a native dialog in main; no renderer or model ever supplies a path to read.
  filesAddFolder: 'files:addFolder', // invoke
  filesRemoveFolder: 'files:removeFolder', // invoke
  filesList: 'files:list', // invoke
  filesStatus: 'files:status', // invoke
  filesReindex: 'files:reindex', // invoke
  filesDeleteIndex: 'files:deleteIndex', // invoke
  filesSearch: 'files:search', // invoke
} as const

export type IpcChannel = (typeof IPC)[keyof typeof IPC]
export type DockMode = 'compact' | 'expanded'

// renderer -> main, request/response
export interface IpcInvokeMap {
  [IPC.stateGet]: { args: []; result: CompanionState }
  [IPC.statePatch]: { args: [patch: RendererStatePatch]; result: void }
  [IPC.settingsGet]: { args: []; result: Settings }
  [IPC.settingsPatch]: { args: [patch: SettingsPatch]; result: Settings }
  [IPC.liveToken]: { args: [personaId: PersonaId]; result: LiveToken }
  [IPC.wakeToken]: { args: []; result: LiveToken }
  [IPC.liveToolCall]: { args: [call: LiveToolCall]; result: unknown }
  [IPC.teachingSystemInstruction]: { args: [personaId: PersonaId]; result: string }
  [IPC.captureLiveFrame]: { args: []; result: LiveFrame }
  [IPC.learnerSnapshot]: { args: []; result: LearnerSnapshot }
  [IPC.learnerMarkdown]: { args: [req: MarkdownEditRequest]; result: MarkdownEditResult }
  [IPC.agentCancel]: { args: [id: string]; result: void }
  [IPC.dockMode]: { args: [mode: DockMode]; result: void }
  [IPC.showtimeStart]: { args: [opts?: ShowtimeStartOptions]; result: void }
  [IPC.showtimeStop]: { args: []; result: void }
  [IPC.showtimeNext]: { args: []; result: void }
  [IPC.showtimePrev]: { args: []; result: void }
  [IPC.showtimePause]: { args: []; result: void }
  [IPC.showtimeState]: { args: []; result: ShowtimeState }
  [IPC.permissionsStatus]: { args: []; result: PermissionStatus }
  [IPC.permissionsRequestMicrophone]: { args: []; result: boolean }
  [IPC.permissionsRequestScreen]: { args: []; result: PermissionStatus }
  [IPC.filesAddFolder]: { args: []; result: AddFolderResult }
  [IPC.filesRemoveFolder]: { args: [path: string]; result: FilesStatus }
  [IPC.filesList]: { args: []; result: FilesStatus }
  [IPC.filesStatus]: { args: []; result: FilesStatus }
  [IPC.filesReindex]: { args: []; result: FilesStatus }
  [IPC.filesDeleteIndex]: { args: []; result: FilesStatus }
  [IPC.filesSearch]: { args: [req: { query: string; k?: number }]; result: FilesSearchResult }
}

// renderer -> main, fire and forget
export interface IpcSendMap {
  [IPC.overlayReady]: [windowSize: { width: number; height: number }]
  [IPC.wakeDetected]: [req: { personaId: PersonaId; source: SessionSource }]
  [IPC.sessionEnded]: [reason: SessionEndReason]
  [IPC.stopPressed]: []
  [IPC.liveTranscript]: [t: LiveTranscript]
  [IPC.liveStatus]: [s: LiveStatus]
  [IPC.confirmAnswer]: [answer: { id: ConfirmRequest['id']; choice: string }]
  [IPC.permissionsOpenSettings]: [pane: PermissionPane]
  [IPC.permissionsRelaunch]: []
  [IPC.permissionsSubscribe]: []
  [IPC.permissionsUnsubscribe]: []
}

// main -> renderer
export interface IpcEventMap {
  [IPC.stateUpdate]: [state: CompanionState]
  [IPC.overlayCmd]: [cmd: OverlayCommand]
  [IPC.sessionStart]: [req: SessionRequest]
  [IPC.sessionStop]: [reason: SessionEndReason]
  [IPC.liveInject]: [msg: LiveInject]
  [IPC.permissionsChanged]: [status: PermissionStatus]
  [IPC.shellCommand]: [cmd: ShellCommand]
  [IPC.showtimeUpdate]: [state: ShowtimeState]
  [IPC.showtimeCue]: [cue: ShowtimeCue]
}

// Typed helper types for invoke/handle/send/on wrappers (used by preload and src/main/ipc.ts).
export type InvokeChannel = keyof IpcInvokeMap
export type InvokeArgs<C extends InvokeChannel> = IpcInvokeMap[C]['args']
export type InvokeResult<C extends InvokeChannel> = IpcInvokeMap[C]['result']
export type SendChannel = keyof IpcSendMap
export type SendArgs<C extends SendChannel> = IpcSendMap[C]
export type EventChannel = keyof IpcEventMap
export type EventArgs<C extends EventChannel> = IpcEventMap[C]

export type Unsubscribe = () => void

// What preload exposes as `window.alongside` (declared in src/renderer/alongside.d.ts).
export interface AlongsideApi {
  getState(): Promise<CompanionState>
  onState(cb: (state: CompanionState) => void): Unsubscribe
  patchState(patch: RendererStatePatch): Promise<void>
  getSettings(): Promise<Settings>
  patchSettings(patch: SettingsPatch): Promise<Settings>

  // overlay window
  overlayReady(size: { width: number; height: number }): void
  onOverlayCommand(cb: (cmd: OverlayCommand) => void): Unsubscribe

  // session lifecycle (dock window)
  wakeDetected(req: { personaId: PersonaId; source: SessionSource }): void
  onSessionStart(cb: (req: SessionRequest) => void): Unsubscribe
  onSessionStop(cb: (reason: SessionEndReason) => void): Unsubscribe
  sessionEnded(reason: SessionEndReason): void
  pressStop(): void

  // Live bridge (dock window)
  live: {
    getToken(personaId: PersonaId): Promise<LiveToken>
    systemInstruction(personaId: PersonaId): Promise<string>
    toolCall(call: LiveToolCall): Promise<unknown>
    onInject(cb: (msg: LiveInject) => void): Unsubscribe
    transcript(t: LiveTranscript): void
    status(s: LiveStatus): void
    liveFrame(): Promise<LiveFrame>
  }

  // wake spotter (dock window)
  wake: {
    getToken(): Promise<LiveToken>
  }

  // user decisions and data
  answerConfirm(answer: { id: string; choice: string }): void
  learnerSnapshot(): Promise<LearnerSnapshot>
  learnerMarkdown(req: MarkdownEditRequest): Promise<MarkdownEditResult>
  cancelAgent(id: string): Promise<void>
  setDockMode(mode: DockMode): Promise<void>

  // SHELL: macOS permissions (the privacy toggles the app needs) and menu-bar commands
  permissions: {
    status(): Promise<PermissionStatus>
    requestMicrophone(): Promise<boolean>
    requestAccessibility(): boolean // opens the system prompt; true when already trusted
    requestScreen(): Promise<PermissionStatus> // runs one capture probe, which makes macOS show its own prompt
    openSettings(pane: PermissionPane): void
    relaunch(): void
    onChange(cb: (status: PermissionStatus) => void): Unsubscribe // main polls only while at least one subscriber exists
  }
  shell: {
    onCommand(cb: (cmd: ShellCommand) => void): Unsubscribe
  }

  // DEMO: Showtime walkthrough (dock button, narration audio in the dock, roadmap strip in the overlay)
  showtime: ShowtimeApi

  // FILES: the local index of folders the user chose (read-only, consent per folder)
  files: {
    addFolder(): Promise<AddFolderResult> // native folder dialog in main
    removeFolder(path: string): Promise<FilesStatus>
    list(): Promise<FilesStatus>
    status(): Promise<FilesStatus>
    reindex(): Promise<FilesStatus>
    deleteIndex(): Promise<FilesStatus>
    search(query: string, k?: number): Promise<FilesSearchResult>
    onStatus(cb: (s: FilesStatus) => void): Unsubscribe
  }
}
