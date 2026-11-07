// End-to-end smoke test of the renderer LiveSession against the real gemini-3.8-live, without a human.
//   node smoke.mjs a        speech in -> audio/transcripts out, point_at tool, interruption flush, injection experiments
//   node smoke.mjs b        >2 minute audio+video session survives (compression), then forced drop + handover resume
// Asserts print PASS/FAIL lines; exit code 1 on any FAIL. API calls are frugal: one session per mode.
import { fakeDesktopJpeg, fakeMic, fakeSpeaker, loadLive, log, mintAuth, realSystemInstruction, recordEvents, sleep, speech, TEST_SYSTEM_INSTRUCTION, waitFor } from './harness.mjs'

const mode = process.argv[2] ?? 'a'
const live = await loadLive()
const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok })
  log(ok ? 'PASS' : 'FAIL', name, detail)
}

function makeSession(extra = {}) {
  const mic = fakeMic()
  const speaker = fakeSpeaker()
  const toolLog = []
  const session = new live.LiveSession({
    host: { getAuth: () => mintAuth('token'), systemInstruction: async () => TEST_SYSTEM_INSTRUCTION },
    audioIn: mic,
    audioOut: speaker,
    model: 'gemini-3.8-live',
    idleTimeoutMs: 0,
    log: () => undefined,
    toolHandler: async (call, signal) => {
      toolLog.push({ at: Date.now(), name: call.name, args: call.args })
      await sleep(600) // simulate grounding latency: the model must keep talking meanwhile
      if (signal.aborted) throw new Error('cancelled')
      if (call.name === 'point_at') {
        const t = String(call.args.target ?? '').toLowerCase()
        return /dino|frobnic|frog/.test(t) ? { found: false, confidence: 0.05, note: 'not visible' } : { found: true, confidence: 0.93 }
      }
      return { ok: true }
    },
    ...extra,
  })
  return { mic, speaker, session, toolLog }
}

const lastAssistantText = (rec, since = 0) =>
  rec.events.filter((e) => e.name === 'transcript' && e.p.role === 'assistant' && e.p.final && e.at >= since).map((e) => e.p.text).join(' ')

async function modeA() {
  const { mic, speaker, session, toolLog } = makeSession()
  const rec = recordEvents(session)
  session.on('transcript', (t) => t.final && log(`  [${t.role}]`, t.text))
  session.on('metrics', (m) => log('  metrics', JSON.stringify(m)))
  session.on('toolCall', (c) => log('  toolCall', c.name, JSON.stringify(c.args)))
  session.on('toolDone', (d) => log('  toolDone', d.name, `${d.ms}ms`, d.error ?? ''))
  session.on('error', (e) => log('  ERROR', JSON.stringify(e)))
  session.on('state', (s) => log('  state', s.phase))

  const t0 = Date.now()
  await session.start({ voiceName: 'Charon' })
  check('session starts (setupComplete)', session.phase === 'live', `${Date.now() - t0}ms`)
  const setupMs = rec.events.find((e) => e.name === 'metrics' && e.p.kind === 'setup')?.p.ms
  await sleep(1500)

  // ---- T1: voice question -> audio + transcripts + point_at, non-blocking ----
  log('--- T1: "Hey, can you show me where the start call button is?"')
  const q1 = speech('q1', 'Hey, can you show me where the start call button is?')
  const bytes0 = speaker.bytes
  const s1 = Date.now()
  await mic.say(q1, { leadMs: 200 })
  const endOfSpeech1 = Date.now()
  await waitFor(session, 'toolDone', (d) => d.name === 'point_at', 20_000).catch(() => undefined)
  await waitFor(session, 'state', (s) => s.phase === 'live', 25_000).catch(() => undefined)
  await sleep(500)
  const toolCall = rec.events.find((e) => e.name === 'toolCall' && e.p.name === 'point_at')
  const toolDone = rec.events.find((e) => e.name === 'toolDone' && e.p.name === 'point_at')
  check('T1 audio comes back', speaker.bytes - bytes0 > 20_000, `${speaker.bytes - bytes0} bytes`)
  check('T1 user transcript arrives', rec.events.some((e) => e.name === 'transcript' && e.p.role === 'user' && e.p.final && e.at >= s1 && /start|call|button/i.test(e.p.text)))
  check('T1 assistant transcript arrives', lastAssistantText(rec, s1).length > 5, JSON.stringify(lastAssistantText(rec, s1)))
  check('T1 point_at tool call emitted', !!toolCall, JSON.stringify(toolCall?.p.args))
  check('T1 point_at response accepted (turn continues, session still live)', !!toolDone && !toolDone.p.error && session.phase !== 'ended')
  const ttfa1 = rec.events.find((e) => e.name === 'metrics' && e.p.kind === 'ttfa' && e.at >= s1)?.p.ms
  const ttfaEnd = (() => {
    const firstAudio = rec.events.find((e) => e.name === 'state' && e.p.phase === 'speaking' && e.at >= s1)
    return firstAudio ? firstAudio.at - endOfSpeech1 : null
  })()
  log(`  TTFA voice: last-voiced-chunk -> first audio = ${ttfa1}ms; end-of-streamed-speech -> first audio = ${ttfaEnd}ms`)
  const audioDuringTool = toolCall && toolDone ? speaker.lastPlayAt >= toolCall.at : false
  log('  audio continued after tool call started (non-blocking evidence):', audioDuringTool)

  // ---- T2: barge-in. Long answer, interrupt mid-way ----
  log('--- T2: long answer, then barge-in')
  const q2 = speech('q2', 'Please explain, step by step and in detail, how I would join a video call with my daughter.')
  const q3 = speech('q3', 'Wait, stop. Hold on a moment please.')
  const s2 = Date.now()
  await mic.say(q2, { leadMs: 200 })
  await waitFor(session, 'state', (s) => s.phase === 'speaking', 15_000).catch(() => undefined)
  await sleep(2500)
  const wasSpeaking = speaker.isPlaying()
  const flushesBefore = speaker.flushes.length
  const bargeAt = Date.now()
  await mic.say(q3, { leadMs: 0 })
  await sleep(1500)
  const intr = rec.events.find((e) => e.name === 'state' && e.at >= bargeAt && e.p.phase !== 'speaking')
  check('T2 model was speaking before barge-in', wasSpeaking)
  check('T2 playback flushed on interruption', speaker.flushes.length > flushesBefore, `flush ${speaker.flushes.length ? speaker.flushes.at(-1) - bargeAt : '-'}ms after user started speaking`)
  check('T2 phase left speaking after interruption', !!intr || session.phase !== 'speaking', intr ? `${intr.at - bargeAt}ms` : '')
  await waitFor(session, 'state', (s) => s.phase === 'live', 25_000).catch(() => undefined)
  await sleep(500)

  // ---- T3: injection while idle ----
  log('--- T3: inject [RUNNER] while idle (realtime text)')
  const i3 = Date.now()
  session.injectText('[RUNNER] Step 1 of 2: ask the learner to look at the green button at the bottom of the video window and tell them to click it when ready.', { interrupt: false })
  await waitFor(session, 'state', (s) => s.phase === 'speaking', 12_000).catch(() => undefined)
  const injTtfa = rec.events.find((e) => e.name === 'metrics' && e.p.kind === 'ttfa' && e.p.trigger === 'text' && e.at >= i3)?.p.ms
  await waitFor(session, 'state', (s) => s.phase === 'live', 25_000).catch(() => undefined)
  check('T3 injected stage direction is spoken', lastAssistantText(rec, i3).length > 5, `ttfa ${injTtfa}ms ${JSON.stringify(lastAssistantText(rec, i3)).slice(0, 120)}`)
  await sleep(500)

  // ---- T4: injection while speaking: does realtime text interrupt? does interrupt:false wait? ----
  log('--- T4: inject while the model is speaking')
  const q4 = speech('q4', 'Tell me everything I should know about the keyboard, slowly, one key group at a time.')
  await mic.say(q4, { leadMs: 200 })
  await waitFor(session, 'state', (s) => s.phase === 'speaking', 15_000).catch(() => undefined)
  await sleep(1200)
  const fl4a = speaker.flushes.length
  const w0 = Date.now()
  session.injectText('[STALL] The learner has not moved for 10 seconds. Offer one short clue.', { interrupt: false })
  await sleep(1500)
  check('T4a interrupt:false does not cut in while speaking (queued)', speaker.flushes.length === fl4a, `flushes ${speaker.flushes.length - fl4a}`)
  await waitFor(session, 'state', (s) => s.phase === 'live', 40_000).catch(() => undefined)
  const waited = Date.now() - w0
  log(`  queued inject delivered after model went idle (waited ~${waited}ms incl. its own speech)`)
  await sleep(2500)
  check('T4a queued stage direction answered after idle', lastAssistantText(rec, w0).length > 5)
  await waitFor(session, 'state', (s) => s.phase === 'live', 25_000).catch(() => undefined)

  // realtime text mid-speech with interrupt:true -> expect `interrupted`?
  const q5 = speech('q5', 'Now describe, in detail, each of the buttons you can see on my screen, one at a time.')
  await mic.say(q5, { leadMs: 200 })
  await waitFor(session, 'state', (s) => s.phase === 'speaking', 15_000).catch(() => undefined)
  await sleep(1500)
  const fl4b = speaker.flushes.length
  session.injectText('[RUNNER] Stop what you are saying. The learner clicked the button. Say well done in four words.', { interrupt: true })
  await sleep(2500)
  const realtimeInterrupts = speaker.flushes.length > fl4b
  log('  realtimeInput.text mid-speech interrupts the model:', realtimeInterrupts)
  await waitFor(session, 'state', (s) => s.phase === 'live', 30_000).catch(() => undefined)

  // ---- T5: INTERRUPT scheduling on a failed point_at ----
  log('--- T5: failed point_at -> INTERRUPT scheduling makes the model speak')
  const q6 = speech('q6', 'Can you show me where the dinosaur icon is on the screen?')
  const s6 = Date.now()
  await mic.say(q6, { leadMs: 200 })
  await waitFor(session, 'toolDone', (d) => d.name === 'point_at', 25_000).catch(() => undefined)
  const doneAt = Date.now()
  await waitFor(session, 'state', (s) => s.phase === 'speaking' && Date.now() > doneAt, 10_000).catch(() => undefined)
  await waitFor(session, 'state', (s) => s.phase === 'live', 30_000).catch(() => undefined)
  const said = lastAssistantText(rec, s6)
  check('T5 model reacts to found:false', /can.?t|cannot|not (see|find)|don.?t see|unable|no .*button/i.test(said), JSON.stringify(said).slice(0, 200))

  // ---- tool-call args sanity ----
  log('tool calls observed:', JSON.stringify(toolLog.map((t) => [t.name, t.args])))
  log(`SETUP ms=${setupMs} | tokens usage events=${rec.byType.metrics}`)
  await session.stop('stop')
  check('stop() emits ended once', rec.events.filter((e) => e.name === 'ended').length === 1)
}

async function modeB() {
  let n = 0
  const frames = {
    grab: async () => ({ jpegBase64: fakeDesktopJpeg(n++ % 6), changeScore: n % 4 === 0 ? 0.2 : 0.0 }),
  }
  const s = makeSession({ frames })
  const sess = s.session
  const rec2 = recordEvents(sess)
  sess.on('transcript', (t) => t.final && log(`  [${t.role}]`, t.text.slice(0, 140)))
  sess.on('error', (e) => log('  ERROR', JSON.stringify(e)))
  sess.on('resumption', (r) => r.reconnected && log('  RESUMPTION', JSON.stringify({ resumed: r.resumed, handle: r.handle ? '<handle>' : null })))
  sess.on('metrics', (m) => m.kind === 'usage' && log('  usage tokens', m.totalTokens))
  sess.on('ended', (e) => log('  ENDED', JSON.stringify(e)))
  const start = Date.now()
  await sess.start({ voiceName: 'Sulafat' })
  check('B session starts with Sulafat voice', sess.phase === 'live')

  const ask = async (name, text) => {
    const pcm = speech(name, text)
    const from = Date.now()
    const bytes = s.speaker.bytes
    await s.mic.say(pcm, { leadMs: 200 })
    await waitFor(sess, 'state', (st) => st.phase === 'speaking', 20_000).catch(() => undefined)
    await waitFor(sess, 'state', (st) => st.phase === 'live', 30_000).catch(() => undefined)
    await sleep(400)
    return { reply: lastAssistantText(rec2, from), audio: s.speaker.bytes - bytes }
  }

  const r0 = await ask('b0', 'Hello. Please remember that my favourite colour is purple. Just say okay.')
  check('B t=0 replies with audio', r0.audio > 5000, JSON.stringify(r0.reply))
  // idle silence with frames until 135 s, with a question every ~40 s
  let nextAsk = 1
  while (Date.now() - start < 140_000) {
    await sleep(1000)
    const el = Date.now() - start
    if (el > nextAsk * 45_000) {
      const r = await ask(`b${nextAsk}`, nextAsk === 1 ? 'What did I say my favourite colour was?' : 'Can you see my screen? Say what colour the large area in the middle of the window is.')
      log(`  t=${(el / 1000) | 0}s reply:`, JSON.stringify(r.reply))
      check(`B t=${(el / 1000) | 0}s still answering (compression keeps the session alive)`, r.audio > 5000 && sess.phase !== 'ended')
      nextAsk++
    }
    if (sess.phase === 'ended') break
  }
  const dur = ((Date.now() - start) / 1000) | 0
  check(`B survived >2 minutes of audio+video (${dur}s)`, dur >= 130 && sess.phase !== 'ended', `frames sent=${sess.frameLoop?.stats.sent} skipped=${sess.frameLoop?.stats.skipped}`)

  // forced unexpected drop -> reconnect with the resumption handle, context preserved
  log('--- forced socket drop (simulating network loss)')
  const hadHandle = !!sess.resumptionHandle
  check('B has a resumption handle before the drop', hadHandle)
  sess.conn.sock.close(4000, 'test drop')
  await waitFor(sess, 'resumption', (r) => r.reconnected, 20_000).then(
    (r) => check('B reconnected after drop', true, `resumed=${r.resumed}`),
    () => check('B reconnected after drop', false),
  )
  const r2 = await ask('b9', 'One more time, what is my favourite colour?')
  check('B context survived the reconnect (answer mentions purple)', /purple/i.test(r2.reply), JSON.stringify(r2.reply))

  // make-before-break handover (what a GoAway triggers)
  log('--- GoAway-style handover')
  sess.conn.handingOver = false
  await sess.conn.handover(6000)
  await sleep(1500)
  const r3 = await ask('b10', 'And what is my favourite colour right now?')
  check('B context survived the make-before-break handover', /purple/i.test(r3.reply) && sess.phase !== 'ended', JSON.stringify(r3.reply))
  await sess.stop('stop')
}

// Quick resumption/handover check (no 2-minute wait).
async function modeT5() {
  const { mic, speaker, session } = makeSession()
  const rec = recordEvents(session)
  session.on('transcript', (t) => t.final && log(`  [${t.role}]`, t.text))
  session.on('toolCall', (c) => log('  toolCall', c.name, JSON.stringify(c.args)))
  session.on('toolDone', (d) => log('  toolDone', d.name, `${d.ms}ms`))
  await session.start({ voiceName: 'Charon' })
  await sleep(1200)
  const s6 = Date.now()
  await mic.say(speech('q6', 'Can you show me where the dinosaur icon is on the screen?'), { leadMs: 200 })
  await waitFor(session, 'toolDone', (d) => d.name === 'point_at', 25_000).catch(() => undefined)
  await sleep(9000) // the INTERRUPT-scheduled reaction to found:false arrives as its own turn after the tool result
  await waitFor(session, 'state', (s) => s.phase === 'live', 30_000).catch(() => undefined)
  const said = lastAssistantText(rec, s6)
  check('T5 model reacts to found:false (INTERRUPT scheduling)', /can.?t|cannot|not (see|find)|don.?t see|unable|no .*icon|isn.?t/i.test(said), JSON.stringify(said).slice(0, 220))
  await session.stop('stop')
}

// P0 regression (QA): a silent session with real screen frames and the REAL teaching prompt must not make the assistant speak
// unprompted, and must end on its own ~20 s after the learner went quiet.
async function modeIdle() {
  const si = await realSystemInstruction('marcus')
  log('real system instruction chars', si.length)
  let n = 0
  const frames = { grab: async () => ({ jpegBase64: fakeDesktopJpeg(n++ % 6), changeScore: 0.2 }) } // a changing screen, every second
  const { session, speaker, mic } = makeSession({ frames, idleTimeoutMs: 0 })
  session.opts.host.systemInstruction = async () => si
  const rec = recordEvents(session)
  session.on('transcript', (t) => t.final && log(`  [${t.role}]`, t.text.slice(0, 120)))
  session.on('notice', (x) => log('  notice', x.kind))
  await session.start({ voiceName: 'Charon' })
  const t0 = Date.now()
  log('--- 45 s of silence (idle timeout disabled) with 1 fps changing frames: the model must stay quiet')
  await sleep(45_000)
  const spoke = speaker.bytes > 0
  const sawAssistantText = rec.events.some((e) => e.name === 'transcript' && e.p.role === 'assistant')
  check('IDLE-1 no unprompted speech during 45 s of silence with changing frames', !spoke && !sawAssistantText, `audio bytes ${speaker.bytes}, assistant lines ${rec.events.filter((e) => e.name === 'transcript' && e.p.role === 'assistant').length}`)
  log('--- enabling the 20 s idle timeout now')
  const t1 = Date.now()
  session.setIdleTimeout(20_000)
  const ended = await waitFor(session, 'ended', () => true, 30_000).then((e) => e, () => null)
  check('IDLE-2 session ends by itself ~20 s after the last learner activity', !!ended && ended.reason === 'idle', ended ? `reason=${ended.reason} after ${((Date.now() - t1) / 1000).toFixed(1)}s` : 'did not end')
  log(`frames sent=${session.frameLoop?.stats.sent}`)
  if (!ended) await session.stop('stop')
  void mic; void t0
}

async function modeC() {
  const s = makeSession({ log: (...a) => log('  [conn]', ...a) })
  const sess = s.session
  const rec = recordEvents(sess)
  sess.on('transcript', (t) => t.final && log(`  [${t.role}]`, t.text.slice(0, 140)))
  sess.on('error', (e) => log('  ERROR', JSON.stringify(e)))
  sess.on('resumption', (r) => r.reconnected && log('  RESUMPTION', JSON.stringify({ resumed: r.resumed })))
  sess.on('state', (st) => log('  state', st.phase, st.reconnecting ? '(reconnecting)' : ''))
  await sess.start({ voiceName: 'Charon' })
  const ask = async (name, text) => {
    const from = Date.now()
    const bytes = s.speaker.bytes
    await s.mic.say(speech(name, text), { leadMs: 200 })
    await waitFor(sess, 'state', (st) => st.phase === 'speaking', 20_000).catch(() => undefined)
    await waitFor(sess, 'state', (st) => st.phase === 'live', 30_000).catch(() => undefined)
    await sleep(400)
    return { reply: lastAssistantText(rec, from), audio: s.speaker.bytes - bytes }
  }
  const r0 = await ask('b0', 'Hello. Please remember that my favourite colour is purple. Just say okay.')
  check('C first turn', r0.audio > 5000)
  await sleep(1500)
  log('--- handover (GoAway-style)')
  const h0 = Date.now()
  await sess.conn.handover(6000)
  log(`  handover returned after ${Date.now() - h0}ms; instances state=${sess.conn.state}`)
  const r1 = await ask('b10', 'What is my favourite colour right now?')
  check('C context survived handover', /purple/i.test(r1.reply) && sess.phase !== 'ended', JSON.stringify(r1.reply))
  await sess.stop('stop')
}

try {
  if (mode === 'idle') await modeIdle()
  else if (mode === 't5') await modeT5()
  else if (mode === 'c') await modeC()
  else if (mode === 'a') await modeA()
  else if (mode === 'b') await modeB()
  else throw new Error('mode must be a|b')
} catch (err) {
  log('SMOKE CRASH', err)
  results.push({ name: 'crash', ok: false })
}
const failed = results.filter((r) => !r.ok)
log(`\n${results.length - failed.length}/${results.length} checks passed${failed.length ? ' | FAILED: ' + failed.map((f) => f.name).join('; ') : ''}`)
process.exit(failed.length ? 1 : 0)
