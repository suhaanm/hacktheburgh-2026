// S-04 (High): the Option-Shift-Command-K path (createKillSwitch.trigger) never writes data/KILL. It sets a process-local boolean and then
// POSTs /kill to the engine and the agent service. The Python MacActuator (and mac_check, the R1 rung) polls only data/KILL, so when neither
// service is running (a standalone mac_check run) the hotkey stops nothing that matters. Fakes only: no network, no desktop.
import fs from 'node:fs'
import path from 'node:path'
import { createKillSwitch } from '../../../apps/desktop/src/main/kill-switch'
import { setKilled } from '../../../apps/desktop/src/main/kill-flag'

const dir = path.join(__dirname, '.tmp-kill')
const REPO_KILL = path.join(__dirname, '../../../data/KILL')
let kill0 = false
beforeEach(() => { kill0 = fs.existsSync(REPO_KILL); globalThis.fetch = (() => { throw new Error('TRIPWIRE: no network in a review test') }) as typeof fetch })
afterEach(() => {
  setKilled(false); fs.rmSync(dir, { recursive: true, force: true }); delete process.env.UNDERSTUDY_DATA_DIR
  if (!kill0 && fs.existsSync(REPO_KILL)) throw new Error('a review test left data/KILL in the REAL data dir')
})

const unreachable = async () => { throw new Error('ECONNREFUSED: neither service is running') }
const noop = () => undefined

it('trigger() leaves a data/KILL file on disk even when the engine and the agent are unreachable', async () => {
  fs.mkdirSync(dir, { recursive: true })
  process.env.UNDERSTUDY_DATA_DIR = dir
  const ks = createKillSwitch({
    stopSession: noop, stopAgency: noop, stopShowtime: noop, cancelConfirm: noop, agents: () => [], cancelAgent: noop,
    overlay: { clear: noop, caption: noop }, engine: { kill: unreachable, clearKill: unreachable },
  })
  await ks.trigger('hotkey')
  expect(ks.isKilled()).toBe(true)                                   // the in-process flag is set...
  expect(fs.existsSync(path.join(dir, 'KILL'))).toBe(true)           // ...but a separate Python process can only see the FILE
})
