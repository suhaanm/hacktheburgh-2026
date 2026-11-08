import { describe, expect, it } from 'vitest'
import { createSseParser } from './sse'

describe('the event stream reader', () => {
  it('reads named events with data, one blank line apart', () => {
    const p = createSseParser()
    expect(p.push('event: snapshot\ndata: {"tasks":[]}\n\nevent: heartbeat\ndata: {"t":"x"}\n\n')).toEqual([
      { event: 'snapshot', data: '{"tasks":[]}' },
      { event: 'heartbeat', data: '{"t":"x"}' },
    ])
  })
  it('waits for the rest of an event that arrives in pieces, even when a piece ends in the middle of a word or a line break', () => {
    const p = createSseParser()
    expect(p.push('event: task_sta')).toEqual([])
    expect(p.push('rted\ndata: {"a"')).toEqual([])
    expect(p.push(':1}\r')).toEqual([])
    expect(p.push('\n\r\n')).toEqual([{ event: 'task_started', data: '{"a":1}' }])
  })
  it('joins several data lines and defaults the name to message', () => {
    const p = createSseParser()
    expect(p.push('data: a\ndata: b\n\n')).toEqual([{ event: 'message', data: 'a\nb' }])
  })
  it('ignores comments and fields it does not use, and a blank line with nothing before it', () => {
    const p = createSseParser()
    expect(p.push(': keep-alive\n\n\nid: 7\nretry: 100\n\nevent: x\ndata: y\n\n')).toEqual([{ event: 'x', data: 'y' }])
  })
  it('takes CRLF and bare CR line ends', () => {
    const p = createSseParser()
    expect(p.push('event: a\r\ndata: 1\r\n\r\nevent: b\rdata: 2\r\r')).toEqual([{ event: 'a', data: '1' }])
    expect(p.push('x')).toEqual([{ event: 'b', data: '2' }])
  })
})
