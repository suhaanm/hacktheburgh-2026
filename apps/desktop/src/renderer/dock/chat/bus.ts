// The chat bus: a tiny renderer-side store that decouples the chat view (DESIGN) from the Live transport (LIVE).
// LIVE pushes transcripts in and registers onSend to carry a typed turn into the Live session; the UI only talks to the bus.

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  final: boolean
  at: number
  via: 'voice' | 'typed'
}

export type ChatMode = 'voice' | 'text'

export interface ChatBus {
  /** Upsert by id. `text` is the cumulative text so far (replace, never append). */
  push(message: ChatMessage): void
  subscribe(cb: (messages: ChatMessage[]) => void): () => void
  /** UI -> controller: a typed user turn. Also shows the user's bubble immediately. */
  send(text: string): void
  /** Controller side: receives typed turns. */
  onSend(cb: (text: string) => void): () => void
  clear(): void
  mode(): ChatMode
  /** `transient` marks a one-off switch (e.g. the menu bar's "Type instead") that must not be saved as a preference. */
  setMode(mode: ChatMode, opts?: { transient?: boolean }): void
  onMode(cb: (mode: ChatMode, info?: { transient: boolean }) => void): () => void
}

const MAX_MESSAGES = 200

export function createChatBus(now: () => number = Date.now): ChatBus {
  let messages: ChatMessage[] = []
  let current: ChatMode = 'voice'
  let counter = 0
  const subscribers = new Set<(m: ChatMessage[]) => void>()
  const senders = new Set<(text: string) => void>()
  const modeListeners = new Set<(m: ChatMode, info?: { transient: boolean }) => void>()

  const publish = (): void => {
    const snapshot = messages.slice()
    subscribers.forEach((cb) => cb(snapshot))
  }

  return {
    push(message) {
      const i = messages.findIndex((m) => m.id === message.id)
      messages = i === -1 ? [...messages, message].slice(-MAX_MESSAGES) : messages.map((m, j) => (j === i ? message : m))
      publish()
    },
    subscribe(cb) {
      subscribers.add(cb)
      cb(messages.slice())
      return () => subscribers.delete(cb)
    },
    send(text) {
      const clean = text.trim()
      if (!clean) return
      const at = now()
      this.push({ id: `typed-${at}-${counter++}`, role: 'user', text: clean, final: true, at, via: 'typed' })
      senders.forEach((cb) => cb(clean))
    },
    onSend(cb) {
      senders.add(cb)
      return () => senders.delete(cb)
    },
    clear() {
      messages = []
      publish()
    },
    mode: () => current,
    setMode(mode, opts) {
      if (mode === current) return
      current = mode
      const info = { transient: opts?.transient === true }
      modeListeners.forEach((cb) => cb(mode, info))
    },
    onMode(cb) {
      modeListeners.add(cb)
      return () => modeListeners.delete(cb)
    },
  }
}

/** The shared instance used by the dock window. */
export const chatBus: ChatBus = createChatBus()
