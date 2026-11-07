// The Showtime script as data: chapters made of timed beats that carry typed actions. A driver executes the
// actions against the real app (or a recorder in tests), so the whole tour is inspectable and testable headlessly.
import type { AnnotationTone, HelpLevel, NormBox, NormPoint, PersonaId, SkillId } from '../../shared/protocol'
import type { ShowtimeDockView } from '../../shared/showtime'

export type Tone = AnnotationTone
// A stage ground id (data-ground-id), or a driver-resolved special target such as '@dock.stop'.
export type TargetRef = string
export interface BoxRef {
  target: TargetRef
  // A phrase inside the target's text: the box is the text range itself (ground truth from the DOM).
  phrase?: string
}

export type AnnSpec =
  | { kind: 'ring'; id: string; target: TargetRef; label?: string; step?: number; tone?: Tone }
  | { kind: 'arrow'; id: string; target: TargetRef; tone?: Tone }
  | { kind: 'tick'; id: string; target: TargetRef; ok?: boolean }
  | { kind: 'highlight'; id: string; boxes: BoxRef[]; note?: string; tone?: Tone }
  | { kind: 'bubble'; id: string; target: TargetRef; text: string; tone?: Tone }
  | { kind: 'bubbleAt'; id: string; at: NormPoint; text: string; tone?: Tone }
  | { kind: 'spotlight'; id: string; target: TargetRef }
  | { kind: 'ghost'; id: string; targets: TargetRef[]; pressAtEnd?: boolean }
  | { kind: 'ringBox'; id: string; box: NormBox; label?: string; tone?: Tone }

// Only these settings are ever flipped by the tour (and restored afterwards).
export interface TourSettingsPatch {
  glass?: boolean
  glassOpacity?: number
  dyslexiaFont?: boolean
  textScale?: number
  theme?: 'system' | 'light' | 'dark'
  highContrast?: boolean
}

export type Action =
  // Injected by the machine whenever a chapter is entered: a known starting point (audio, annotations, chips, skill, persona, settings).
  | { type: 'baseline'; persona: PersonaId }
  | { type: 'stage.go'; route: string }
  | { type: 'stage.click'; target: TargetRef }
  | { type: 'stage.deliverScam' }
  | { type: 'stage.hide' }
  | { type: 'stage.show' }
  | { type: 'ann.show'; specs: AnnSpec[] }
  | { type: 'ann.clear'; ids?: string[] }
  | { type: 'say'; line: string }
  | { type: 'caption'; speaker: 'user' | 'assistant' | 'system'; text: string }
  | { type: 'persona'; id: PersonaId }
  | { type: 'phase'; phase: 'listening_for_name' | 'connecting' | 'live' | 'thinking' | 'speaking' }
  | { type: 'level'; to: HelpLevel; reason: string; scope: 'attempt' | 'step' }
  | { type: 'skill'; skill: { id: SkillId; name: string; step: number; stepCount: number } | null }
  | { type: 'settings'; patch: TourSettingsPatch }
  | { type: 'agent'; op: 'start' | 'progress' | 'done'; text?: string }
  | { type: 'dock.view'; view: ShowtimeDockView }
  | { type: 'dock.chat'; id: string; role: 'user' | 'assistant'; text: string }
  | { type: 'profile.forget'; match: string }
  | { type: 'progress.seed' }
  | { type: 'agency.request' }
  | { type: 'agency.approve' }
  | { type: 'agency.audit' }
  | { type: 'files.search'; query: string }

export interface Beat {
  at: number
  action: Action
}

export type Requirement = 'agency' | 'files'

export interface Chapter {
  id: string
  n: number
  title: string
  caption: string
  persona: PersonaId
  durationMs: number
  requires: Requirement[]
  beats: Beat[]
}

export interface ScriptLine {
  id: string
  chapter: string
  persona: PersonaId
  text: string
  durationMs: number
  full?: boolean
}
