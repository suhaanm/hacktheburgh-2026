import { describe, expect, it } from 'vitest'
import { LIVE_TOOL_NAMES as SHARED_TOOL_NAMES, ToolArgSchemas } from '../../src/shared/protocol'
import { LIVE_TOOLS, isBlockingTool, schedulingFor } from '../../src/renderer/live/tools'
import { buildSetup, liveUrl, parseDurationMs, parseServerMessage, pcm16ToBase64Chunks, msg } from '../../src/renderer/live/wire'

describe('parseServerMessage', () => {
  it('processes every field of a bundled message, transcription before interrupted/turnComplete', () => {
    const events = parseServerMessage({
      serverContent: {
        modelTurn: { parts: [{ inlineData: { data: 'AAAA', mimeType: 'audio/pcm;rate=24000' } }] },
        outputTranscription: { text: 'Hello ' },
        inputTranscription: { text: 'hi' },
        interrupted: true,
        turnComplete: true,
        interactionStatus: 'IDLE',
      },
      usageMetadata: { totalTokenCount: 321 },
    })
    expect(events.map((e) => e.type)).toEqual(['audio', 'inputTranscription', 'outputTranscription', 'interrupted', 'turnComplete', 'usage'])
    expect(events.find((e) => e.type === 'turnComplete')).toMatchObject({ interactionStatus: 'IDLE' })
  })

  it('parses tool calls, cancellation (top level and nested), goAway and resumption', () => {
    const calls = parseServerMessage({ toolCall: { functionCalls: [{ id: 'a', name: 'point_at', args: { target: 'x' } }, { name: 'clear_annotations' }] } })
    expect(calls[0]).toMatchObject({ type: 'toolCall' })
    expect((calls[0] as { calls: Array<{ id: string; args: unknown }> }).calls[0]).toEqual({ id: 'a', name: 'point_at', args: { target: 'x' } })
    expect((calls[0] as { calls: Array<{ id: string }> }).calls[1]!.id).toBeTruthy()
    expect(parseServerMessage({ toolCallCancellation: { ids: ['a', 'b'] } })).toEqual([{ type: 'toolCallCancellation', ids: ['a', 'b'] }])
    expect(parseServerMessage({ serverContent: { toolCallCancellation: { ids: ['c'] } } })).toEqual([{ type: 'toolCallCancellation', ids: ['c'] }])
    expect(parseServerMessage({ goAway: { timeLeft: '50s' } })).toEqual([{ type: 'goAway', timeLeftMs: 50_000 }])
    expect(parseServerMessage({ sessionResumptionUpdate: { newHandle: 'h1', resumable: true } })).toEqual([{ type: 'resumptionUpdate', handle: 'h1', resumable: true }])
    // Not resumable while generating: no handle, flagged false.
    expect(parseServerMessage({ sessionResumptionUpdate: { newHandle: '', resumable: false } })).toEqual([{ type: 'resumptionUpdate', handle: null, resumable: false }])
  })

  it('ignores junk', () => {
    expect(parseServerMessage(null)).toEqual([])
    expect(parseServerMessage('x')).toEqual([])
    expect(parseServerMessage({ serverContent: { modelTurn: { parts: [null, 5, {}] } } })).toEqual([])
  })

  it('parses protobuf durations', () => {
    expect(parseDurationMs('1.5s')).toBe(1500)
    expect(parseDurationMs({ seconds: 2, nanos: 500_000_000 })).toBe(2500)
    expect(parseDurationMs(undefined)).toBe(0)
  })
})

describe('buildSetup', () => {
  const base = { model: 'gemini-3.8-live', voiceName: 'Charon', systemInstruction: 'be kind', tools: LIVE_TOOLS }

  it('turns on compression, resumption and both transcriptions from the first message, and never sends thinkingConfig', () => {
    const { setup } = buildSetup(base)
    expect(setup.model).toBe('models/gemini-3.8-live')
    expect(setup.contextWindowCompression).toEqual({ slidingWindow: {} })
    expect(setup.sessionResumption).toEqual({})
    expect(setup.inputAudioTranscription).toEqual({})
    expect(setup.outputAudioTranscription).toEqual({})
    const gc = setup.generationConfig as Record<string, unknown>
    expect(gc.responseModalities).toEqual(['AUDIO'])
    expect(gc.thinkingConfig).toBeUndefined()
    expect(JSON.stringify(gc.speechConfig)).toContain('Charon')
  })

  it('passes the resumption handle on reconnect', () => {
    expect(buildSetup({ ...base, resumptionHandle: 'abc' }).setup.sessionResumption).toEqual({ handle: 'abc' })
  })

  it('builds URLs for ephemeral tokens (constrained endpoint) and keys', () => {
    expect(liveUrl({ kind: 'token', value: 'auth_tokens/x y' })).toContain('BidiGenerateContentConstrained?access_token=auth_tokens%2Fx%20y')
    expect(liveUrl({ kind: 'key', value: 'k' })).toContain('BidiGenerateContent?key=k')
  })
})

describe('messages', () => {
  it('frames audio, video, text and tool responses the way the API expects', () => {
    expect(msg.audio('QQ==')).toEqual({ realtimeInput: { audio: { data: 'QQ==', mimeType: 'audio/pcm;rate=16000' } } })
    expect(msg.video('QQ==')).toEqual({ realtimeInput: { video: { data: 'QQ==', mimeType: 'image/jpeg' } } })
    expect(msg.text('hi')).toEqual({ realtimeInput: { text: 'hi' } })
    expect(msg.toolResponse([{ id: '1', name: 'n', response: { a: 1 }, scheduling: 'SILENT' }])).toEqual({
      toolResponse: { functionResponses: [{ id: '1', name: 'n', response: { a: 1 }, scheduling: 'SILENT' }] },
    })
  })

  it('chunks pre-roll PCM into base64 pieces', () => {
    const pcm = new Int16Array(4000).fill(1000)
    const chunks = pcm16ToBase64Chunks(pcm)
    expect(chunks).toHaveLength(3)
    expect(atob(chunks[0]!).length).toBe(3200)
    expect(atob(chunks[2]!).length).toBe(1600)
  })
})

describe('tool declarations', () => {
  it('declare exactly the shared Live tools', () => {
    expect(LIVE_TOOLS.map((t) => t.name).sort()).toEqual([...SHARED_TOOL_NAMES].sort())
  })

  it('have unique names (a duplicate declaration would make the server refuse the setup)', () => {
    const names = LIVE_TOOLS.map((t) => t.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it('are NON_BLOCKING except ask_user_confirm', () => {
    for (const t of LIVE_TOOLS) expect(t.behavior).toBe(t.name === 'ask_user_confirm' ? 'BLOCKING' : 'NON_BLOCKING')
    expect(isBlockingTool('ask_user_confirm')).toBe(true)
    expect(isBlockingTool('point_at')).toBe(false)
  })

  it('require the same args the dispatcher validates', () => {
    const requiredByDispatcher: Record<string, string[]> = {
      point_at: ['target'],
      start_lesson: ['goal'],
      verify_step: ['expected_outcome'],
      spawn_agent: ['kind', 'task'],
      ask_user_confirm: ['question', 'options'],
      update_profile: ['note'],
      end_lesson: ['summary'],
      set_help_level: ['level'],
    }
    for (const [name, req] of Object.entries(requiredByDispatcher)) {
      expect(LIVE_TOOLS.find((t) => t.name === name)!.parameters!.required, name).toEqual(req)
    }
    // A sample call built from each declaration parses with the shared zod schema.
    expect(ToolArgSchemas.spawn_agent.safeParse({ kind: 'scam_check', task: 't', payload: { useScreen: true } }).success).toBe(true)
    expect(ToolArgSchemas.ask_user_confirm.safeParse({ question: 'q', options: ['a', 'b'] }).success).toBe(true)
    const kinds = LIVE_TOOLS.find((t) => t.name === 'spawn_agent')!.parameters!.properties!.kind!.enum
    expect(kinds).toEqual(['scam_check', 'lookup', 'lesson_summary'])
  })

  it('schedules results: failed pointing interrupts, blocking tools have none', () => {
    expect(schedulingFor('point_at', { found: false })).toBe('INTERRUPT')
    expect(schedulingFor('point_at', { found: true })).toBe('SILENT')
    expect(schedulingFor('verify_step', { completed: true })).toBe('WHEN_IDLE')
    expect(schedulingFor('ask_user_confirm', { choice: 'a' })).toBeUndefined()
    expect(schedulingFor('point_at', { error: 'boom' })).toBe('WHEN_IDLE')
  })
})
