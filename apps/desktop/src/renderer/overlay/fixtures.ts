// Fixture annotation sets for the headless render harness (demo.html?fixture=<name>).
// They target the generated mock desktop in backdrop.tsx (MOCK below) so a ring really sits on a button.
import type { Annotation, NormBox, OverlayCommand } from '../../shared/protocol'

export interface Fixture {
  description: string
  commands: OverlayCommand[]
  settings?: { bigAnnotations?: boolean; highContrast?: boolean; dyslexiaFont?: boolean; captions?: boolean }
  // Freeze the ghost cursor: 'flight' = mid first leg, 'press' = landed with the click echo, or ms.
  ghost?: 'flight' | 'press' | number
  // Freeze the level-chip echo mid-change (0 before .. 1 after).
  chip?: number
}

const box = (xmin: number, ymin: number, xmax: number, ymax: number): NormBox => ({ xmin, ymin, xmax, ymax })

// Norm-space layout of the mock desktop (x right, y down, 0-1000).
export const MOCK = {
  videoWindow: box(50, 90, 640, 880),
  videoTile: box(90, 160, 600, 560),
  mic: box(150, 650, 215, 735),
  camera: box(245, 650, 310, 735),
  share: box(340, 650, 405, 735),
  chat: box(435, 650, 500, 735),
  hangUp: box(530, 650, 600, 735),
  messagesWindow: box(670, 90, 960, 880),
  scamBubble: box(690, 330, 940, 560),
  scamLine1: box(705, 370, 925, 398),
  scamLine2: box(705, 405, 880, 433),
  scamLink: box(705, 470, 905, 498),
  sendButton: box(850, 780, 940, 840),
  settingsIcon: box(900, 20, 955, 70),
} as const


const centre = (b: NormBox): { x: number; y: number } => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })

const show = (...annotations: Annotation[]): OverlayCommand => ({ type: 'show', annotations })

const stepRing = (id: string, b: NormBox, step: number, label: string): Annotation => ({ id, kind: 'ring', tone: 'guide', box: b, step, label })

const combo: OverlayCommand[] = [
  show(
    stepRing('r1', MOCK.share, 1, 'Share your screen'),
    { id: 'a1', kind: 'arrow', tone: 'guide', to: MOCK.share },
    { id: 'bub', kind: 'bubble', tone: 'guide', at: centre(MOCK.hangUp), text: 'Leave this one for last.' },
  ),
  { type: 'caption', speaker: 'assistant', text: 'Click the button with the arrow on it. That shares what you see.', final: true },
  { type: 'chip', level: 2, label: 'Walk with me' },
]

export const FIXTURES: Record<string, Fixture> = {
  'ring-badge': {
    description: 'Numbered rings on two buttons (ring + step badge + label).',
    commands: [show(stepRing('r1', MOCK.mic, 1, 'Mute'), stepRing('r2', MOCK.camera, 2, 'Camera'), { id: 'b3', kind: 'badge', tone: 'guide', at: { x: 565, y: 640 }, n: 3 })],
  },
  'arrow-box': {
    description: 'Arrow to a box (auto direction) and an arrow with an explicit start.',
    commands: [show({ id: 'a1', kind: 'arrow', tone: 'guide', to: MOCK.share }, { id: 'a2', kind: 'arrow', tone: 'warn', to: MOCK.hangUp, from: { x: 600, y: 820 } })],
  },
  'arrow-point': {
    description: 'Arrow to a bare point near the top-right corner (must stay on screen).',
    commands: [show({ id: 'a1', kind: 'arrow', tone: 'guide', to: centre(MOCK.settingsIcon) })],
  },
  spotlight: {
    description: 'Spotlight (dim everything but one button) with its ring label.',
    commands: [show({ id: 's1', kind: 'spotlight', tone: 'guide', box: MOCK.share }, { id: 'r1', kind: 'ring', tone: 'guide', box: MOCK.share, label: 'Share' })],
  },
  'ghost-flight': {
    description: 'Ghost cursor mid-flight along mic -> camera -> share (trail visible).',
    ghost: 'flight',
    commands: [show({ id: 'g1', kind: 'ghostCursor', tone: 'guide', path: [centre(MOCK.mic), centre(MOCK.share), centre(MOCK.hangUp)] })],
  },
  'ghost-press': {
    description: 'Ghost cursor landed with the click echo (a picture of a click, not a click).',
    ghost: 'press',
    commands: [show({ id: 'g1', kind: 'ghostCursor', tone: 'guide', path: [centre(MOCK.mic), centre(MOCK.share)], pressAtEnd: true }, { id: 'r1', kind: 'ring', tone: 'guide', box: MOCK.share })],
  },
  'highlight-text': {
    description: 'Three scam red flags highlighted with a note.',
    commands: [show({ id: 'h1', kind: 'highlightText', tone: 'danger', boxes: [MOCK.scamLine1, MOCK.scamLine2, MOCK.scamLink], note: 'Banks never ask for this' })],
  },
  'tick-ok': {
    description: 'Verification tick (step done).',
    commands: [show({ id: 't1', kind: 'tick', tone: 'success', box: MOCK.camera, ok: true })],
  },
  'tick-fail': {
    description: 'Gentle "not yet" mark (a miss is warn, never danger).',
    commands: [show({ id: 't1', kind: 'tick', tone: 'warn', box: MOCK.camera, ok: false })],
  },
  bubble: {
    description: 'Speech bubble anchored on a button.',
    commands: [show({ id: 'b1', kind: 'bubble', tone: 'guide', at: centre(MOCK.hangUp), text: 'This one ends the call. Leave it for last.' })],
  },
  captions: {
    description: 'Captions band plus the level chip echo.',
    commands: [
      { type: 'caption', speaker: 'assistant', text: 'Click the round button with the little camera on it. It turns your picture on.', final: true },
      { type: 'chip', level: 2, label: 'Walk with me' },
    ],
  },
  'chip-before': {
    description: 'Level chip echo before a change: Watch me, all four support bars full.',
    commands: [{ type: 'chip', level: 1, label: 'Watch me' }],
  },
  'chip-mid': {
    description: 'Level chip echo mid-change (Watch me -> Nudge me): the top bars are draining and the old label is fading out.',
    chip: 0.4,
    commands: [{ type: 'chip', level: 1, label: 'Watch me' }, { type: 'chip', level: 3, label: 'Nudge me' }],
  },
  'chip-after': {
    description: 'Level chip echo after the change: Nudge me, two bars left.',
    chip: 1,
    commands: [{ type: 'chip', level: 1, label: 'Watch me' }, { type: 'chip', level: 3, label: 'Nudge me' }],
  },
  'caption-avoids': {
    description: 'A target low on the screen (call controls): the captions band moves to the top, below the level chip, instead of covering the ring.',
    commands: [
      show({ id: 'r1', kind: 'ring', tone: 'guide', box: { xmin: 150, ymin: 880, xmax: 250, ymax: 965 }, step: 2, label: 'Mute' }, { id: 'a1', kind: 'arrow', tone: 'guide', to: { xmin: 150, ymin: 880, xmax: 250, ymax: 965 } }),
      { type: 'caption', speaker: 'assistant', text: 'Check the microphone is not crossed out. Click it once if it is.', final: true },
      { type: 'chip', level: 2, label: 'Walk with me' },
    ],
  },
  tones: {
    description: 'All four tones side by side (colour is never the only cue).',
    commands: [
      show(
        { id: 't1', kind: 'ring', tone: 'guide', box: MOCK.mic, label: 'Look here' },
        { id: 't2', kind: 'ring', tone: 'success', box: MOCK.camera, label: 'Done' },
        { id: 't3', kind: 'ring', tone: 'warn', box: MOCK.share, label: 'Take care' },
        { id: 't4', kind: 'ring', tone: 'danger', box: MOCK.hangUp, label: 'Stop and check' },
      ),
    ],
  },
  'big-off': { description: 'Combined L2 step, normal sizes.', settings: { bigAnnotations: false }, commands: combo },
  'big-on': { description: 'Combined L2 step, bigAnnotations (x1.6).', settings: { bigAnnotations: true }, commands: combo },
  'high-contrast': { description: 'Combined L2 step, high contrast.', settings: { highContrast: true, bigAnnotations: false }, commands: combo },
}
