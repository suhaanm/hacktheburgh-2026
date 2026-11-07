// The wire between main and the Cue panel page: what the page is asked to show (a CueView) and the few things it may ask for back
// (a CueCardAction). Types and channel names only, no Electron: the preload, the page, main and the storyboard all import this.
// The page never sees a decision, an episode id or a box: only the words and the keys on the screen.

export const CUE_IPC = {
  get: 'cue:get', // invoke: the current view
  view: 'cue:view', // main -> page
  action: 'cue:action', // page -> main
  size: 'cue:size', // page -> main: the card's measured size, so the window can be exactly that big
} as const

export interface CueWhyView {
  reason: string | null
  phrase: string | null
  // The path probability comes from simulated experts: a small tag says so.
  simulated: boolean
}

export interface CueChipView {
  mode: 'chip'
  text: string
  // The mono step number (help level 1 only).
  stepN: number | null
  why: CueWhyView | null
  // The popover under the chip is open.
  open: boolean
  // "Show me" is offered when there is a target to demonstrate on and the demonstration has not played.
  canShowMe: boolean
  // The chip is the card's collapsed answer, waiting for the engine's cue for the chosen step.
  pending: boolean
}

export interface CueQuestionView {
  mode: 'question'
  question: string
  options: Array<{ id: string; label: string; key: string }>
  // "Something else": always last, quiet.
  other: { key: string; label: string }
  // The key chord prefix shown on the key caps ("⌥" on a Mac).
  chord: string
}

export interface CueOfferView {
  mode: 'offer'
  text: string
}

export type CueViewBody = CueChipView | CueQuestionView | CueOfferView

// `seq` changes for every new cue (the page cross-fades on it); `from` says the view grew out of another one (the question collapsing into a chip).
export type CueView = ({ seq: number; from?: 'question' } & CueViewBody) | null

export type CueCardAction =
  | { type: 'answer'; id: string }
  | { type: 'other' }
  | { type: 'dismiss' }
  | { type: 'why'; open: boolean }
  | { type: 'show_me' }
  | { type: 'know_this' }
  | { type: 'offer'; yes: boolean }
  // The pointer is on the panel: the worker is looking at it, so the "untouched" clocks restart.
  | { type: 'touch' }

export interface CueCardApi {
  get(): Promise<CueView>
  onView(cb: (v: CueView) => void): () => void
  action(a: CueCardAction): void
  size(s: { w: number; h: number }): void
}

declare global {
  interface Window {
    understudyCue?: CueCardApi
  }
}
