import { describe, expect, it } from 'vitest'
import { LIVE_ENDPOINT_URL, buildSetup, msg, parseServerMessage, pcmSeconds, silenceBase64 } from './wire'
import { buildToolDeclarations } from './tools'

const tools = buildToolDeclarations({ items: [{ id: 'a', label: 'A' }] })

describe('buildSetup', () => {
  it('has no credential in the endpoint, no thinkingConfig, and asks for audio and resumption but for NO transcript of either side', () => {
    expect(LIVE_ENDPOINT_URL).not.toMatch(/key=|access_token=|token=/i)
    const { setup } = buildSetup({ model: 'm', voiceName: 'Sulafat', systemInstruction: 'x', tools })
    expect((setup.generationConfig as any).thinkingConfig).toBeUndefined()
    expect((setup.generationConfig as any).responseModalities).toEqual(['AUDIO'])
    expect(setup.inputAudioTranscription).toBeUndefined()
    expect(setup.outputAudioTranscription).toBeUndefined()
    expect(setup.sessionResumption).toEqual({})
    expect(setup.model).toBe('models/m')
  })
  it('manual turn mode turns the server detector off; vad mode keeps it on', () => {
    expect((buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, turnMode: 'manual' }).setup.realtimeInputConfig as any).automaticActivityDetection).toEqual({ disabled: true })
    expect((buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools }).setup.realtimeInputConfig as any).automaticActivityDetection.disabled).toBe(false)
  })
  it('a transcription-only turn declares no tools; a text model answers in text', () => {
    expect(buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, transcribeOnly: true }).setup.tools).toBeUndefined()
    expect((buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, transcribeOnly: true, textOnly: true }).setup.generationConfig as any).responseModalities).toEqual(['TEXT'])
  })
  it('bounds the provider context: a compression trigger and target when asked', () => {
    expect(buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, compressionTriggerTokens: 8000, compressionTargetTokens: 4000 }).setup.contextWindowCompression).toEqual({ triggerTokens: 8000, slidingWindow: { targetTokens: 4000 } })
    expect(buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools }).setup.contextWindowCompression).toEqual({ slidingWindow: {} })
  })
  it('asks for the input transcript only when Cue listens for an answer, and never for the model\'s own words', () => {
    const s = buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, transcribeOnly: true, inputTranscript: true }).setup
    expect(s.inputAudioTranscription).toEqual({})
    expect(s.outputAudioTranscription).toBeUndefined()
  })
  it('resumes with a handle when given one', () => {
    expect(buildSetup({ model: 'm', voiceName: 'v', systemInstruction: 'x', tools, resumptionHandle: 'h' }).setup.sessionResumption).toEqual({ handle: 'h' })
  })
})

describe('messages', () => {
  it('builds the realtimeInput shapes verified against the service', () => {
    expect(msg.audio('AAAA')).toEqual({ realtimeInput: { audio: { data: 'AAAA', mimeType: 'audio/pcm;rate=16000' } } })
    expect(msg.video('/9j/')).toEqual({ realtimeInput: { video: { data: '/9j/', mimeType: 'image/jpeg' } } })
    expect(msg.audioStreamEnd()).toEqual({ realtimeInput: { audioStreamEnd: true } })
    expect(msg.activityStart()).toEqual({ realtimeInput: { activityStart: {} } })
    expect(msg.toolResponse([{ id: '1', name: 'x', response: {}, scheduling: 'SILENT' }])).toEqual({ toolResponse: { functionResponses: [{ id: '1', name: 'x', response: {}, scheduling: 'SILENT' }] } })
  })
  it('measures PCM seconds without decoding', () => {
    expect(pcmSeconds(silenceBase64(1000, 16000), 16000)).toBeCloseTo(1, 2)
    expect(pcmSeconds(silenceBase64(500, 16000), 16000)).toBeCloseTo(0.5, 2)
    expect(pcmSeconds('', 16000)).toBe(0)
  })
})

describe('parseServerMessage', () => {
  it('reads usage per modality from the shape the live service sends', () => {
    const [ev] = parseServerMessage({ usageMetadata: { promptTokenCount: 564, responseTokenCount: 24, totalTokenCount: 588, promptTokensDetails: [{ modality: 'TEXT', tokenCount: 317 }, { modality: 'AUDIO', tokenCount: 222 }], responseTokensDetails: [{ modality: 'AUDIO', tokenCount: 24 }], thoughtsTokenCount: 54 } })
    expect(ev).toMatchObject({ type: 'usage', usage: { promptTokens: 564, responseTokens: 24, thoughtsTokens: 54, promptDetails: [{ modality: 'TEXT', tokenCount: 317 }, { modality: 'AUDIO', tokenCount: 222 }] } })
  })
  it('processes every field of a bundled message, audio before turnComplete', () => {
    const types = parseServerMessage({ serverContent: { modelTurn: { parts: [{ inlineData: { data: 'AA', mimeType: 'audio/pcm;rate=24000' } }] }, outputTranscription: { text: 'hi' }, generationComplete: true, turnComplete: true }, usageMetadata: { totalTokenCount: 5 } }).map((e) => e.type)
    expect(types).toEqual(['audio', 'outputTranscription', 'generationComplete', 'turnComplete', 'usage'])
  })
  it('ignores malformed input and tool calls without a name', () => {
    expect(parseServerMessage(null)).toEqual([])
    expect(parseServerMessage({ toolCall: { functionCalls: [{ id: 'x' }, 5] } })).toEqual([])
    expect(parseServerMessage({ toolCall: { functionCalls: [{ id: 'x', name: 'point_at', args: { description: 'a' } }] } })[0]).toMatchObject({ type: 'toolCall' })
  })
})
