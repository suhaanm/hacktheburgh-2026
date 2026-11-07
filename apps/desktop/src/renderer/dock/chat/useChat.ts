import { useEffect, useState } from 'react'
import type { CaptionLine } from '../../../shared/protocol'
import { chatBus, type ChatMessage, type ChatMode } from './bus'

export function useChatMessages(): ChatMessage[] {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  useEffect(() => chatBus.subscribe(setMessages), [])
  return messages
}

export function useChatMode(): ChatMode {
  const [mode, setMode] = useState<ChatMode>(chatBus.mode())
  useEffect(() => chatBus.onMode(setMode), [])
  return mode
}

/**
 * What the conversation shows. Messages in the bus win. Until the Live transport has pushed any, the older
 * main-process captions stand in, so the view is never empty while someone is talking.
 */
export function conversationFrom(messages: readonly ChatMessage[], captions: readonly CaptionLine[]): { messages: ChatMessage[]; asides: string[] } {
  if (messages.length > 0) return { messages: [...messages], asides: [] }
  const spoken = captions.filter((c): c is CaptionLine & { speaker: 'user' | 'assistant' } => c.speaker !== 'system')
  return {
    messages: spoken.map((c) => ({ id: c.id, role: c.speaker, text: c.text, final: c.final, at: c.at, via: 'voice' as const })),
    asides: captions.filter((c) => c.speaker === 'system').slice(-1).map((c) => c.text),
  }
}
