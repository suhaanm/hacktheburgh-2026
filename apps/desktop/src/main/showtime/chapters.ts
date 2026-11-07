// The eleven chapters of the walkthrough as timed beats. The core cut targets about 2:50; `full` adds extra
// narration and a few more interactions for the extended tour. Times come from the narration slots, not magic numbers.
import { PERSONAS } from '../../shared/personas'
import { SCRIPT_LINES } from './script'
import { Timeline } from './timeline'
import type { Action, AnnSpec, Chapter, ScriptLine } from './types'

export interface BuildOptions {
  full: boolean
  lines?: Map<string, ScriptLine>
}

const skill = (step: number): Action => ({ type: 'skill', skill: { id: 'video_call', name: 'Start a video call', step, stepCount: 4 } })
const noSkill: Action = { type: 'skill', skill: null }
const ring = (id: string, target: string, step?: number, label?: string): AnnSpec => ({ kind: 'ring', id, target, step, label, tone: 'guide' })
const arrow = (id: string, target: string): AnnSpec => ({ kind: 'arrow', id, target, tone: 'guide' })
const tick = (id: string, target: string): AnnSpec => ({ kind: 'tick', id, target, ok: true })
const show = (...specs: AnnSpec[]): Action => ({ type: 'ann.show', specs })
const clear = (...ids: string[]): Action => ({ type: 'ann.clear', ids: ids.length ? ids : undefined })
const click = (target: string): Action => ({ type: 'stage.click', target })
const go = (route: string): Action => ({ type: 'stage.go', route })
const view = (v: 'now' | 'chat' | 'progress' | 'profile' | 'settings'): Action => ({ type: 'dock.view', view: v })
const userSays = (text: string): Action => ({ type: 'caption', speaker: 'user', text })
const level = (to: 1 | 2 | 3 | 4, reason: string, scope: 'attempt' | 'step'): Action => ({ type: 'level', to, reason, scope })

// A click takes about a second in the driver (the demo cursor travels, then presses), so the next beat waits for it.
const CLICK_MS = 1000
const SCAM_MESSAGE = 'messages.msg.scam.0'

export function buildChapters({ full, lines = SCRIPT_LINES }: BuildOptions): Chapter[] {
  const tl = (): Timeline => new Timeline(lines)
  const chapters: Chapter[] = []
  const add = (c: Omit<Chapter, 'durationMs' | 'beats'>, t: Timeline, tailMs?: number): void => {
    chapters.push({ ...c, beats: t.beats, durationMs: t.end(tailMs) })
  }
  const marcus = PERSONAS.marcus.displayName
  const amelia = PERSONAS.amelia.displayName

  // 1. Say its name
  {
    const t = tl()
    t.do(go('desktop'), { type: 'phase', phase: 'listening_for_name' }, view('now'))
    t.wait(600).do(userSays(`Hey ${marcus}.`))
    t.wait(1100).do({ type: 'phase', phase: 'connecting' })
    t.wait(600).do({ type: 'phase', phase: 'live' }).say('c1-hello', { block: true })
    if (full) t.wait(300).say('c1-more', { block: true })
    add({ id: 'say-its-name', n: 1, title: 'Say its name', caption: 'Say its name, or press a key. It listens only then.', persona: 'marcus', requires: [] }, t)
  }

  // 2. It shows, you do (video_call at "Walk with me")
  {
    const t = tl()
    t.do(go('desktop'), skill(1))
    t.wait(300).do(show(ring('r1', 'desk.icon.video', 1, 'VideoChat'), arrow('a1', 'desk.icon.video'))).say('c2-1')
    t.wait(3500).do(click('desk.icon.video'))
    t.wait(CLICK_MS).do(clear('r1', 'a1'), show(tick('t1', 'desk.icon.video')), skill(2))
    if (full) t.wait(300).say('c2-2')
    t.wait(500).do({ type: 'caption', speaker: 'assistant', text: 'Good. Now Lily.' }, show(ring('r2', 'video.contact.lily', 2, 'Lily'), arrow('a2', 'video.contact.lily')))
    if (full) {
      t.wait(700).do(show({ kind: 'ring', id: 'decoy', target: 'video.toolbar.join', label: 'Not this one', tone: 'warn' })).say('c2-wrong', { block: true })
      t.do(clear('decoy'))
    }
    t.wait(1300).do(click('video.contact.lily'))
    t.wait(CLICK_MS).do(clear('r2', 'a2'), show(tick('t2', 'video.contact.lily')), skill(3))
    t.wait(400).do(show(ring('r3', 'video.start_call', 3, 'Start call'), arrow('a3', 'video.start_call'))).say('c2-3')
    t.wait(1700).do(click('video.start_call'))
    t.wait(CLICK_MS).do(clear('r3', 'a3'), show(tick('t3', 'video.start_call')), skill(4))
    t.wait(400).do(show(ring('r4', 'video.precall.join', 4, 'Join'), arrow('a4', 'video.precall.join'))).say('c2-4', { block: true })
    t.wait(300).do(click('video.precall.join'))
    t.wait(CLICK_MS + 1300).do(clear('r4', 'a4'), show(tick('t4', 'video.call.main_video')), noSkill)
    t.say('c2-5', { block: true })
    // Teaching beat: the spoken teach-back (the product asks it after every task; the answer is a recorded fixture).
    t.wait(200).do({ type: 'caption', speaker: 'system', text: 'Teach-back: you explain it, so it sticks.' }).say('c2-tb', { block: true })
    t.wait(400).do(userSays('It starts the call with Lily.'))
    t.wait(500).say('c2-tb2', { block: true })
    if (full) t.wait(300).say('c2-tech', { block: true })
    add({ id: 'it-shows-you-do', n: 2, title: 'It shows, you do', caption: 'A ring and a number show each step. A tick says it worked.', persona: 'marcus', requires: [] }, t)
  }

  // 3. Less help as you learn (chip drains L2 -> L3, a scripted stall: glow, clue, arrow; the hints chart)
  {
    const t = tl()
    t.do({ type: 'progress.seed' }, go('video/lily'), skill(3))
    t.wait(200).do(level(3, 'two clean steps in a row', 'attempt'), { type: 'caption', speaker: 'system', text: 'Two clean steps: help steps back from Walk with me to Nudge me.' }).say('c3-1', { block: true })
    t.say('c3-2', { block: true })
    t.wait(800).do(show({ kind: 'ring', id: 'glow', target: 'video.start_call', tone: 'guide' }))
    t.wait(1000).do(show({ kind: 'bubble', id: 'clue', target: 'video.start_call', text: "Look for the big green button under Lily's name.", tone: 'guide' })).say('c3-3', { block: true })
    t.do(clear('glow', 'clue'), level(2, 'stalled on this step, so this step gets an arrow', 'step'), show(ring('r3', 'video.start_call', 3, 'Start call'), arrow('a3', 'video.start_call')))
    t.wait(1300).do(click('video.start_call'))
    t.wait(CLICK_MS).do(clear('r3', 'a3'), show(tick('t3', 'video.start_call')), level(3, 'step done, help fades again', 'step'), noSkill)
    t.wait(400).do(view('progress')).say('c3-4', { block: true })
    if (full) t.wait(300).say('c3-5', { block: true }).say('c3-tech', { block: true })
    add({ id: 'less-help', n: 3, title: 'Less help as you learn', caption: 'The level chip drops as you get it right. A stall gets a nudge, then more help.', persona: 'marcus', requires: [] }, t)
  }

  // 4. Scam Shield (recorded report, real chip + highlight machinery)
  {
    const t = tl()
    const stepMs = full ? 2200 : 1100
    t.do(go('desktop'), view('now'))
    t.wait(300).do({ type: 'stage.deliverScam' }).say('c4-1')
    t.wait(1800).do(go('messages/scam'))
    t.wait(400).do({ type: 'agent', op: 'start', text: 'Checking this message…' })
    if (full) t.say('c4-4')
    const msgs = ['Checking the link…', 'Checking the wording…', 'Checking who it says it is…', 'Putting it together…']
    for (const m of msgs) t.wait(stepMs).do({ type: 'agent', op: 'progress', text: m })
    t.wait(stepMs).do({ type: 'agent', op: 'done', text: 'Likely a scam. Do not tap the link.' })
    t.untilQuiet()
    t.do(show({ kind: 'highlight', id: 'flag-urgent', boxes: [{ target: SCAM_MESSAGE, phrase: 'URGENT' }], note: 'It rushes you', tone: 'danger' })).say('c4-2')
    t.wait(1700).do(show({ kind: 'highlight', id: 'flag-threat', boxes: [{ target: SCAM_MESSAGE, phrase: 'your money will be frozen' }], note: 'It threatens you', tone: 'danger' }))
    t.wait(1700).do(show({ kind: 'highlight', id: 'flag-link', boxes: [{ target: 'messages.link.scam' }], note: 'An odd web address', tone: 'danger' }))
    t.untilQuiet().wait(300).do({ type: 'caption', speaker: 'assistant', text: 'I can’t be sure. Ring the number on your bank card.' }).say('c4-3', { block: true })
    if (full) t.wait(300).say('c4-5', { block: true })
    add({ id: 'scam-shield', n: 4, title: 'Scam Shield', caption: 'A suspicious text is checked, the warning signs are marked, and it never says "safe".', persona: 'marcus', requires: [] }, t)
  }

  // 5. Meet the second helper (persona switch: voice and accent)
  {
    const t = tl()
    t.do(go('desktop'), view('now'))
    t.wait(500).do(userSays(`Hey ${amelia}.`))
    t.wait(900).do({ type: 'phase', phase: 'connecting' }, { type: 'persona', id: 'amelia' })
    t.wait(600).do({ type: 'phase', phase: 'live' }).say('c5-1', { block: true })
    if (full) t.wait(300).say('c5-2', { block: true })
    add({ id: 'second-helper', n: 5, title: 'Meet the second helper', caption: 'A second helper with her own voice and colour. The rules stay the same.', persona: 'marcus', requires: [] }, t)
  }

  // 6. Teach me anything (a goal with no saved lesson: one step, one ring)
  {
    const t = tl()
    t.do(go('video/call-screen'), { type: 'skill', skill: { id: 'custom', name: 'Mute yourself', step: 1, stepCount: 1 } })
    t.wait(300).do(userSays('How do I mute myself?')).wait(700).say('c6-1', { block: true })
    t.do(show(ring('r1', 'video.call.mic', 1, 'Mute'), arrow('a1', 'video.call.mic'))).say('c6-2', { block: true })
    t.wait(300).do(click('video.call.mic'))
    t.wait(CLICK_MS).do(clear('r1', 'a1'), show(tick('t1', 'video.call.mic')), noSkill).say('c6-3', { block: true })
    if (full) t.wait(300).say('c6-tech', { block: true })
    add({ id: 'teach-anything', n: 6, title: 'Teach me anything', caption: 'Ask about something it has no lesson for: it works out one ring from your screen.', persona: 'amelia', requires: [] }, t)
  }

  // 7. I can do it for you, only if you say so (real confirm modal; demo approve is automated and labelled)
  {
    const t = tl()
    t.do(go('desktop'))
    t.wait(300).do(userSays('Can you open the Age UK website for me?')).wait(500).say('c7-1')
    t.wait(2500).do({ type: 'agency.request' })
    t.wait(2300).do({ type: 'caption', speaker: 'system', text: 'Demo approve: in real use this is your own click.' }, { type: 'agency.approve' })
    t.wait(700).do({ type: 'stage.hide' })
    t.untilQuiet().say('c7-2')
    t.wait(1400).do({ type: 'agency.audit' })
    t.wait(3600).do({ type: 'stage.show' })
    t.untilQuiet()
    if (full) t.say('c7-3', { block: true })
    add({ id: 'do-it-for-you', n: 7, title: 'I can do it for you', caption: 'Only if you say so: you confirm first, and every action is logged.', persona: 'marcus', requires: ['agency'] }, t)
  }

  // 8. Your files (recorded search result)
  {
    const t = tl()
    t.do(go('desktop'))
    t.wait(300).do(userSays('Where did I save my GP letter?')).wait(500).do({ type: 'files.search', query: 'GP letter' }).say('c8-1', { block: true })
    if (full) t.wait(300).say('c8-2', { block: true })
    t.wait(600)
    add({ id: 'your-files', n: 8, title: 'Your files', caption: 'It finds your own files, only in folders you chose, and only reads them.', persona: 'marcus', requires: ['files'] }, t)
  }

  // 9. Type instead (chat view, voice off)
  {
    const t = tl()
    t.do(go('video/call-screen'), view('chat'))
    t.wait(700).do({ type: 'dock.chat', id: 'q1', role: 'user', text: 'What does Join mean?' })
    t.wait(1400).do({ type: 'dock.chat', id: 'a1', role: 'assistant', text: 'Join means: connect to the call. Press it once and Lily will see and hear you.' })
    t.wait(2500).do({ type: 'dock.chat', id: 'q2', role: 'user', text: 'What if I press the wrong button?' })
    t.wait(1400).do({ type: 'dock.chat', id: 'a2', role: 'assistant', text: 'Nothing breaks. Press the red Leave button to end the call, then try again.' })
    t.wait(1800)
    if (full) {
      t.say('c9-tech', { block: true })
    }
    add({ id: 'type-instead', n: 9, title: 'Type instead', caption: 'Prefer typing? Same helper, answers appear as chat, no voice.', persona: 'marcus', requires: [] }, t)
  }

  // 10. You're in control (look and feel, forget a line, Stop)
  {
    const t = tl()
    t.do(go('settings/display'), view('settings'))
    t.wait(300).say('c10-1')
    t.wait(900).do({ type: 'settings', patch: { glass: true, glassOpacity: 0.78 } })
    t.wait(1200).do({ type: 'settings', patch: { dyslexiaFont: true } })
    t.wait(1200).do({ type: 'settings', patch: { textScale: 1.25 } })
    if (full) t.wait(1200).do({ type: 'settings', patch: { theme: 'dark' } })
    t.untilQuiet().wait(300).do(view('profile')).say('c10-2')
    t.wait(4600).do({ type: 'profile.forget', match: 'Comparing the contacts list' })
    t.untilQuiet().wait(300).do(view('now'), show({ kind: 'ring', id: 'stop', target: '@dock.stop', label: 'Stop', tone: 'warn' })).say('c10-3', { block: true })
    if (full) t.wait(300).say('c10-4', { block: true })
    add({ id: 'in-control', n: 10, title: "You're in control", caption: 'Change how it looks, make it forget a line, or press Stop at any time.', persona: 'marcus', requires: [] }, t)
  }

  // 11. Progress, then hand over to live Q&A
  {
    const t = tl()
    t.do({ type: 'progress.seed' }, go('desktop'), view('progress'))
    t.wait(300).say('c11-1', { block: true })
    if (full) t.wait(300).say('c11-tech', { block: true })
    t.say('c11-2', { block: true })
    add({ id: 'progress', n: 11, title: 'Progress', caption: 'What you can do now, and your hints per task going down. Now ask it anything.', persona: 'marcus', requires: [] }, t)
  }

  return chapters
}
