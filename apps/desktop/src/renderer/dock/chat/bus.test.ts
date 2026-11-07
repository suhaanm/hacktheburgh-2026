import { describe, expect, it } from 'vitest'
import { createChatBus, type ChatMessage } from './bus'

const msg = (over: Partial<ChatMessage> = {}): ChatMessage => ({ id: 'a', role: 'assistant', text: 'Hello', final: false, at: 1, via: 'voice', ...over })

describe('chat bus', () => {
  it('upserts by id with cumulative text and keeps order', () => {
    const bus = createChatBus()
    const seen: ChatMessage[][] = []
    bus.subscribe((m) => seen.push(m))
    bus.push(msg())
    bus.push(msg({ text: 'Hello there', final: true }))
    bus.push(msg({ id: 'b', role: 'user', text: 'Hi' }))
    const last = seen[seen.length - 1]!
    expect(last.map((m) => [m.id, m.text, m.final])).toEqual([['a', 'Hello there', true], ['b', 'Hi', false]])
  })

  it('send shows the typed bubble and hands the text to the controller', () => {
    const bus = createChatBus(() => 1000)
    const sent: string[] = []
    bus.onSend((t) => sent.push(t))
    let latest: ChatMessage[] = []
    bus.subscribe((m) => (latest = m))
    bus.send('  how do I mute myself?  ')
    bus.send('   ')
    expect(sent).toEqual(['how do I mute myself?'])
    expect(latest).toHaveLength(1)
    expect(latest[0]).toMatchObject({ role: 'user', via: 'typed', final: true, text: 'how do I mute myself?' })
  })

  it('mode changes notify once and unsubscribe works', () => {
    const bus = createChatBus()
    const seen: string[] = []
    const off = bus.onMode((m) => seen.push(m))
    expect(bus.mode()).toBe('voice')
    bus.setMode('text')
    bus.setMode('text')
    off()
    bus.setMode('voice')
    expect(seen).toEqual(['text'])
  })

  it('a transient mode switch is flagged so it is not saved as a preference', () => {
    const bus = createChatBus()
    const seen: [string, boolean | undefined][] = []
    bus.onMode((m, info) => seen.push([m, info?.transient]))
    bus.setMode('text', { transient: true })
    bus.setMode('voice')
    expect(seen).toEqual([['text', true], ['voice', false]])
  })

  it('clear empties the log', () => {
    const bus = createChatBus()
    bus.push(msg())
    bus.clear()
    let latest: ChatMessage[] = [msg()]
    bus.subscribe((m) => (latest = m))
    expect(latest).toEqual([])
  })
})
