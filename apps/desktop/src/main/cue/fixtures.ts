// Cue fixtures: one decision per kind and tier, in the shape the engine sends (services/engine/understudy_engine/cue/types.py, as raw
// JSON so they also exercise the parser), plus malformed inputs that must all become `none`. The fake poller (source.ts) plays them; the
// storyboard harness and the tests use them. Boxes are nominal ([y0, x0, y1, x1] on the 0..1000 grid) for the harness stand-in page at
// 1440 by 900; the harness re-measures them from the page. Everything here is synthetic: the pack is the UK benefits processor, the
// labels and reason lines are the engine's own pack vocabulary, the path probabilities are simulated experts.

export type Box = [number, number, number, number]

export const STEP_READ_CASE = { id: 'read_case', label: 'Read the household record', reason_id: 'why.read_case', reason_text: 'The record holds the facts every calculator needs.', n: 1 } as const
export const STEP_CALC_A = { id: 'calc_a', label: 'Run calculator A', reason_id: 'why.enter_once', reason_text: 'Copy the household from the record; retyping invites mistakes.', n: 2 } as const
export const STEP_CLIFF_A = { id: 'cliff_a', label: 'Check cliff edges (A)', reason_id: 'why.cliff', reason_text: 'A figure near a limit can flip the answer.', n: 3 } as const
export const STEP_WRITE_NOTE = { id: 'write_note', label: 'Copy figures to the note', reason_id: 'why.note', reason_text: 'A note that names its evidence can be checked later.', n: 6 } as const

// Nominal boxes on the 0..1000 grid, matching the stand-in page's layout at 1440 by 900.
export const BOX: Record<string, Box> = {
  read_case: [167, 83, 500, 306],
  calc_a: [622, 347, 673, 444],
  cliff_a: [767, 347, 796, 486],
  write_note: [222, 681, 467, 917],
}

const base = { episode_id: 'ep-0042', budget_left: 2, cooldown_s: 90, source: 'rule', new: true } as const

const WHY = (level: 1 | 2 | 3 | 4, pathProb = 0.78, reasons: string[] = ['stuck_signal', 'path_confident', 'grounded_dom']) => ({ path_prob: pathProb, margin: 0.41, p_stuck: 0.72, mastery: 0.31, level, reasons, origin: 'synthetic' })
const TARGET = (box: Box) => ({ box_2d: box, source: 'dom', confidence: 0.93 })

export const FIXTURES: Record<string, unknown> = {
  none: { kind: 'none', episode_id: 'ep-0042', why: { reasons: ['not_stuck'] } },

  // Silent confirmation after retrieval practice: a tick on the step, no words, help was withheld.
  confirm: { ...base, kind: 'confirm', tier: null, retrieval: true, step: STEP_CALC_A, target: TARGET(BOX.calc_a), say: { chip: null, whisper: null }, why: WHY(4, 0.9, ['retrieval_withheld']) },

  // Tier 1: a ring and nothing else (what level 3 looks like: a thinner ring, no chip).
  'cue-t1-l3': { ...base, kind: 'cue', tier: 1, step: STEP_CALC_A, target: TARGET(BOX.calc_a), say: { chip: 'Next: Run calculator A', whisper: null }, why: WHY(3) },
  // Tier 2 at level 2: ring and one chip.
  'cue-t2-l2': { ...base, kind: 'cue', tier: 2, step: STEP_CALC_A, target: TARGET(BOX.calc_a), say: { chip: 'Next: Run calculator A', whisper: null }, why: WHY(2, 0.78, ['stuck_signal', 'path_confident', 'grounded_dom', 'escalated']) },
  // Tier 2 at level 1: ring, chip and the step pill.
  'cue-t2-l1': { ...base, kind: 'cue', tier: 2, step: STEP_CLIFF_A, target: TARGET(BOX.cliff_a), say: { chip: 'Next: Check cliff edges (A)', whisper: null }, why: WHY(1, 0.88) },
  // Tier 3: adds the ghost-cursor demonstration of the expert's move.
  'cue-t3': { ...base, kind: 'cue', tier: 3, step: STEP_WRITE_NOTE, target: TARGET(BOX.write_note), say: { chip: 'Next: Copy figures to the note', whisper: null }, why: WHY(1, 0.91, ['stuck_signal', 'escalated', 'long_stall']) },
  // Tier 4: a whisper (voice). The words are the pack line's caption; the audio is a cached clip named by whisper_id.
  'cue-t4': { ...base, kind: 'cue', tier: 4, step: STEP_WRITE_NOTE, target: TARGET(BOX.write_note), say: { chip: 'Next: Copy figures to the note', whisper: 'Next, copy the figures across.', whisper_id: 'whisper.write_note' }, why: WHY(1, 0.91, ['stuck_signal', 'escalated', 'long_stall']) },
  // A cue with nothing to ring (the box failed the sanity checks upstream): the chip stands alone.
  'cue-no-target': { ...base, kind: 'cue', tier: 2, step: STEP_CALC_A, target: { box_2d: null, source: 'none', confidence: 0 }, say: { chip: 'Next: Run calculator A', whisper: null }, why: WHY(2, 0.78, ['stuck_signal', 'ungrounded']) },

  // The question: the top two candidates are close, or the screen is unclear. The engine appends the fixed "other" option.
  'ask-3': {
    ...base,
    kind: 'ask',
    tier: null,
    step: null,
    target: TARGET(BOX.calc_a),
    options: [
      { id: 'calc_a', label: 'Run calculator A' },
      { id: 'cliff_a', label: 'Check cliff edges (A)' },
      { id: 'write_note', label: 'Copy figures to the note' },
      { id: 'other', label: 'Something else' },
    ],
    question: { type: 'close_call', text: 'Which of these is next?' },
    say: { chip: null, whisper: null },
    why: WHY(2, 0.41, ['stuck_signal', 'path_close_call']),
  },
  'ask-4': {
    ...base,
    kind: 'ask',
    tier: null,
    step: null,
    target: null,
    options: [
      { id: 'read_case', label: 'Read the household record' },
      { id: 'calc_a', label: 'Run calculator A' },
      { id: 'cliff_a', label: 'Check cliff edges (A)' },
      { id: 'write_note', label: 'Copy figures to the note' },
      { id: 'other', label: 'Something else' },
    ],
    question: { type: 'unclear', text: 'I cannot tell where you are. What is next?' },
    say: { chip: null, whisper: null },
    why: WHY(2, 0.33, ['stuck_signal', 'ungrounded']),
  },
  'ask-2': {
    ...base,
    kind: 'ask',
    tier: null,
    step: null,
    target: TARGET(BOX.read_case),
    options: [
      { id: 'read_case', label: 'Read the household record' },
      { id: 'calc_a', label: 'Run calculator A' },
      { id: 'other', label: 'Something else' },
    ],
    question: { type: 'screen_disagrees', text: 'I can see more than one option. Which is next?' },
    say: { chip: null, whisper: null },
    why: WHY(2, 0.47, ['stuck_signal', 'screen_disagrees']),
  },

  // After a long stall: a small "want a hand?".
  offer: { ...base, kind: 'offer', tier: null, step: STEP_CALC_A, target: TARGET(BOX.calc_a), say: { chip: 'Want a hand?', whisper: null }, why: WHY(2, 0.78, ['stuck_signal', 'long_stall']) },
}

/** Every one of these must parse to `none`. */
export const MALFORMED: Array<{ name: string; raw: unknown }> = [
  { name: 'not an object', raw: 'cue' },
  { name: 'null', raw: null },
  { name: 'array', raw: [] },
  { name: 'unknown kind', raw: { kind: 'takeover', episode_id: 'ep-1', tier: 2, say: { chip: 'Do it for me' } } },
  { name: 'missing episode id', raw: { kind: 'cue', tier: 2, target: TARGET(BOX.calc_a), say: { chip: 'Hello' } } },
  { name: 'episode id with a path in it', raw: { kind: 'cue', episode_id: '../../etc/passwd', tier: 2, target: TARGET(BOX.calc_a), say: { chip: 'Hello' } } },
  { name: 'cue without a tier', raw: { kind: 'cue', episode_id: 'ep-1', target: TARGET(BOX.calc_a), say: { chip: 'Hello' } } },
  { name: 'cue with tier 9', raw: { kind: 'cue', episode_id: 'ep-1', tier: 9, target: TARGET(BOX.calc_a), say: { chip: 'Hello' } } },
  { name: 'cue with nothing to show', raw: { kind: 'cue', episode_id: 'ep-1', tier: 1, target: { box_2d: null, source: 'none', confidence: 0 }, say: { chip: '' } } },
  { name: 'cue whose box is NaN and has no words', raw: { kind: 'cue', episode_id: 'ep-1', tier: 1, target: { box_2d: [Number.NaN, 0, 10, 10], source: 'dom', confidence: 1 }, say: { chip: null } } },
  { name: 'cue whose box covers the screen and has no words', raw: { kind: 'cue', episode_id: 'ep-1', tier: 1, target: { box_2d: [0, 0, 1000, 1000], source: 'vision', confidence: 0.9 }, say: { chip: '' } } },
  { name: 'ask with one option', raw: { kind: 'ask', episode_id: 'ep-1', options: [{ id: 'a', label: 'Only one' }], say: { chip: 'Which?' } } },
  { name: 'ask with one option plus other', raw: { kind: 'ask', episode_id: 'ep-1', options: [{ id: 'a', label: 'Only one' }, { id: 'other', label: 'Something else' }], question: { type: 'close_call', text: 'Which?' } } },
  { name: 'ask with duplicate options', raw: { kind: 'ask', episode_id: 'ep-1', options: [{ id: 'a', label: 'A' }, { id: 'a', label: 'A again' }], say: { chip: 'Which?' } } },
  { name: 'ask with options that are not objects', raw: { kind: 'ask', episode_id: 'ep-1', options: ['a', 'b', 'c'], say: { chip: 'Which?' } } },
  { name: 'ask with option ids that are not ids', raw: { kind: 'ask', episode_id: 'ep-1', options: [{ id: '<img onerror=x>', label: 'A' }, { id: 'b c', label: 'B' }], say: { chip: 'Which?' } } },
  { name: 'offer with no words', raw: { kind: 'offer', episode_id: 'ep-1', say: { chip: null } } },
  { name: 'confirm without a box', raw: { kind: 'confirm', episode_id: 'ep-1', say: { chip: null } } },
  { name: 'kind is an object', raw: { kind: { x: 1 }, episode_id: 'ep-1' } },
]
