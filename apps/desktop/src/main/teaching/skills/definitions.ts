// Static facts about the three skills we teach. Pure data; no I/O. Fallback lesson plans live in plans.ts.
import { BUILTIN_SKILL_IDS } from '../../../shared/protocol'
import type { BuiltinSkillId, SkillId } from '../../../shared/protocol'

// UK Essential Digital Skills categories (framework tagging for credibility; see research/04 section 1.6).
export type EdsCategory = 'communicating' | 'safe_and_legal' | 'foundation'

export interface SkillDefinition {
  id: SkillId
  // Learner-facing names. `name` is a task ("Start a video call"), `shortName` a noun phrase for tables.
  name: string
  shortName: string
  edsCategory: EdsCategory
  // "Things you can do now" wording, in the learner's own goals language.
  canDo: string
  // One analogy per skill; never stack metaphors.
  analogy: string
  // Jargon -> plain words, used by the prompt when explainJargon is on.
  jargonMap: Record<string, string>
  // Matches a spoken goal to this skill.
  keywords: RegExp[]
  // Key points a good teach-back covers (the model scores against these; see prompts.ts).
  teachBackRubric: string[]
  // One "point to it" retrieval question asked after the task.
  retrievalQuestion: string
  commonMistakes: string[]
}

const BUILTIN_DEFS: Record<BuiltinSkillId, SkillDefinition> = {
  video_call: {
    id: 'video_call',
    name: 'Start a video call',
    shortName: 'Video call',
    edsCategory: 'communicating',
    canDo: 'Start a video call with someone you know',
    analogy: 'A video call is a phone call where you can also see each other.',
    jargonMap: {
      app: 'a little program on the screen',
      icon: 'a small picture you tap',
      contact: 'a person saved in the list',
      permission: 'the computer asking if it may use the camera',
    },
    keywords: [/\bvideo\b/i, /\bface ?time\b/i, /\bzoom\b/i, /\bwhats ?app\b/i, /\bskype\b/i, /\b(?:call|ring|phone|speak to|talk to|see)\b.*\b(?:lily|granddaughter|grandson|daughter|son|family|friend|mum|dad)\b/i, /\bcall (?:her|him|them)\b/i],
    teachBackRubric: ['open the video app', 'pick the person from the list', 'press the green video call button', 'say yes to the camera question'],
    retrievalQuestion: 'Can you point to the button that starts the video call?',
    commonMistakes: ['presses the phone-only call button instead of the video button', 'says no to the camera question and thinks it is broken'],
  },
  spot_scam: {
    id: 'spot_scam',
    name: 'Spot a scam message',
    shortName: 'Spot a scam',
    edsCategory: 'safe_and_legal',
    canDo: 'Spot a message that is trying to trick you',
    analogy: 'A scam message is like a stranger at the door who is in a big hurry and wants your money or your details.',
    jargonMap: {
      link: 'a blue underlined address you can tap to open a page',
      phishing: 'a trick message that pretends to be someone you trust',
      sender: 'who the message says it is from',
    },
    keywords: [/\bscam/i, /\bsuspicious\b/i, /\bfraud/i, /\bphish/i, /\bfake\b/i, /\b(?:is|was) (?:this|that) (?:message|text|email) (?:real|genuine|safe|ok|okay)\b/i, /\bcheck (?:this|that|a|the) (?:message|text|email)\b/i, /\bparcel\b/i, /\btrick/i],
    teachBackRubric: ['do not tap the link', 'real companies do not rush you', 'check using the official app or the number on your card', 'ask someone you trust'],
    retrievalQuestion: 'Can you point to the part of the message that is rushing you?',
    commonMistakes: ['taps the link to see what happens', 'replies to the sender', 'trusts a message because it looks professional'],
  },
  bigger_text: {
    id: 'bigger_text',
    name: 'Make the text bigger',
    shortName: 'Bigger text',
    edsCategory: 'foundation',
    canDo: 'Make the writing on the screen bigger',
    analogy: 'Text size is like a volume knob for the writing: turn it up until it is comfortable.',
    jargonMap: {
      settings: 'the place where you change how the computer looks and behaves',
      slider: 'a bar with a round handle you slide left or right',
      display: 'how the screen looks',
    },
    keywords: [/\b(?:bigger|larger|big|large|enlarge)\b/i, /\btext size\b/i, /\bfont\b/i, /\bcan'?t read\b/i, /\btoo small\b/i, /\bsmall (?:writing|text|print|letters)\b/i, /\bmagnif/i, /\bsettings\b/i, /\bzoom (?:in|the text)\b/i],
    teachBackRubric: ['open Settings', 'find the text size control', 'slide it until the writing is comfortable', 'you can always change it back'],
    retrievalQuestion: 'Can you point to the control that makes the writing bigger?',
    commonMistakes: ['slides it the wrong way', 'closes settings before seeing the result'],
  },
}

// 'custom' is the one generic skill behind every Argon-planned lesson (goals outside the three built-ins).
const CUSTOM_DEF: SkillDefinition = {
  id: 'custom',
  name: 'Something new',
  shortName: 'Something new',
  edsCategory: 'foundation',
  canDo: 'Work out a new task on the screen with help',
  analogy: 'Finding your way around a new place is easier when someone walks the first stretch with you.',
  jargonMap: {},
  keywords: [],
  teachBackRubric: [],
  retrievalQuestion: 'Can you point to where you would do that?',
  commonMistakes: [],
}

export const SKILLS: Record<SkillId, SkillDefinition> = { ...BUILTIN_DEFS, custom: CUSTOM_DEF }

export const BUILTIN_SKILL_LIST: SkillDefinition[] = BUILTIN_SKILL_IDS.map((id) => SKILLS[id])
export const SKILL_LIST: SkillDefinition[] = Object.values(SKILLS)

export function skillName(id: SkillId): string {
  return SKILLS[id].name
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()
}

// Used by the markdown parser: accepts ids, long names and short names, any case.
export function matchSkillName(text: string): SkillId | null {
  const n = norm(text)
  if (!n) return null
  for (const def of SKILL_LIST) {
    if (n === norm(def.id) || n === norm(def.name) || n === norm(def.shortName)) return def.id
  }
  return null
}

// Goal text -> skill. Highest keyword hit count wins; ties go to the earlier skill in SKILL_LIST order.
export function pickSkill(goal: string): BuiltinSkillId | null {
  let best: { id: BuiltinSkillId; hits: number } | null = null
  for (const def of BUILTIN_SKILL_LIST) {
    const hits = def.keywords.reduce((n, re) => n + (re.test(goal) ? 1 : 0), 0)
    if (hits > 0 && (!best || hits > best.hits)) best = { id: def.id as BuiltinSkillId, hits }
  }
  return best ? best.id : null
}
