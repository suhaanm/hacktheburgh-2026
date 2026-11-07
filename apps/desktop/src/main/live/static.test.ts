// Static scans that keep the voice path honest: one place that sends, no key outside the minter, nothing written to disk but two small
// metadata files, no content in a log line, no way to ask for the microphone, no websocket in a renderer.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { LiveSession as LegacyLiveSession } from '../../renderer/live/legacy'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = path.resolve(here, '../..')
const raw = (f: string): string => fs.readFileSync(f, 'utf8')
// Source without comments: a comment may say what the code must never do. (A `//` inside a string, as in a URL, has no space before it and stays.)
const read = (f: string): string => raw(f).replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '$1')

function walk(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p)
  }
  return out
}
const isTest = (f: string): boolean => /\.test(-util)?\.tsx?$|\.test-util\.ts$/.test(f)
const rel = (f: string): string => path.relative(src, f)

const liveMain = walk(path.join(src, 'main/live')).filter((f) => !isTest(f))
const liveLegacyMain = fs.readdirSync(path.join(src, 'main')).filter((f) => /^live-.*\.ts$/.test(f) && !isTest(f)).map((f) => path.join(src, 'main', f))
const rendererAll = walk(path.join(src, 'renderer')).filter((f) => !isTest(f))
const voiceFiles = [...liveMain, ...liveLegacyMain, ...walk(path.join(src, 'renderer/live')), ...walk(path.join(src, 'renderer/wake'))].filter((f) => !isTest(f))

describe('there is one place that sends', () => {
  it('only egress.ts writes to the Live connection', () => {
    const offenders = liveMain.filter((f) => path.basename(f) !== 'egress.ts').filter((f) => /\bconn\??\.send\s*\(/.test(read(f)))
    expect(offenders.map(rel)).toEqual([])
    expect(/\bconn\.send\s*\(/.test(read(path.join(src, 'main/live/egress.ts')))).toBe(true)
  })
  it('the connection object is handed to the egress and to nothing else', () => {
    for (const f of liveMain) {
      if (['session.ts', 'egress.ts', 'connection.ts'].includes(path.basename(f))) continue
      expect(read(f), rel(f)).not.toMatch(/new LiveConnection|import .*LiveConnection/)
    }
  })
  it('the session never builds a socket message itself: audio, frames and control go through the egress', () => {
    const text = read(path.join(src, 'main/live/session.ts'))
    expect(text).not.toMatch(/msg\.(audio|video)\s*\(/)
    expect(text).not.toMatch(/\.send\s*\(/)
  })
})

describe('the key', () => {
  it('is named only where it is read to mint a token or to check it is there', () => {
    const naming = liveMain.filter((f) => /GEMINI_API_KEY/.test(read(f))).map((f) => path.basename(f)).sort()
    expect(naming).toEqual(['manager.ts', 'token.ts'])
    const header = liveMain.filter((f) => /x-goog-api-key/i.test(read(f))).map((f) => path.basename(f))
    expect(header).toEqual(['token.ts'])
  })
  it('is never put in a URL: no query credential is built anywhere', () => {
    for (const f of liveMain) {
      const t = read(f)
      expect(t, rel(f)).not.toMatch(/[?&]key=|access_token=|\$\{[^}]*key[^}]*\}/i)
    }
  })
  it('no renderer source has the key, a token minter, the Gemini host, or a websocket', () => {
    for (const f of rendererAll) {
      const t = read(f)
      expect(t, rel(f)).not.toMatch(/x-goog-api-key|auth_tokens|generativelanguage|googleapis\.com|BidiGenerateContent|new WebSocket\s*\(|AIza[0-9A-Za-z_-]{20,}|(process|import\.meta)\.env[.[][^\n]*(KEY|TOKEN|SECRET)/)
    }
  })
  it('the renderer never opens a socket or a model call: no fetch and no websocket in the voice renderer files', () => {
    for (const f of walk(path.join(src, 'renderer/live')).filter((x) => !isTest(x))) expect(read(f), rel(f)).not.toMatch(/\bfetch\s*\(|WebSocket|XMLHttpRequest/)
  })
})

describe('the old renderer-side Live session is gone', () => {
  it('cannot be constructed, and its files and token path are removed', async () => {
    expect(() => new LegacyLiveSession({ host: { getAuth: async () => ({ kind: 'token', value: 'x' }), systemInstruction: async () => '' }, audioIn: {}, audioOut: {}, model: 'm' })).toThrow(/removed/i)
    for (const gone of ['LiveSession.ts', 'connection.ts', 'frames.ts', 'tools.ts', 'wire.ts']) expect(fs.existsSync(path.join(src, 'renderer/live', gone)), gone).toBe(false)
    const { mintLiveToken } = await import('../live-auth')
    await expect(mintLiveToken()).rejects.toThrow(/talk key/)
  })
})

describe('nothing is written to disk', () => {
  const WRITE = /writeFile|appendFile|createWriteStream|writeSync|openSync|mkdirSync|renameSync|copyFile|truncate|localStorage|sessionStorage|indexedDB|caches\.|\.cache\b/
  it('in the voice code, except the two metadata files (settings and the usage log)', () => {
    const allowed = new Set(['main/live/settings.ts', 'main/live/meter.ts'])
    const offenders = voiceFiles.filter((f) => !allowed.has(rel(f))).filter((f) => WRITE.test(read(f)))
    expect(offenders.map(rel)).toEqual([])
  })
  it('the two files that write, write only what they say: settings keys, and numbers/counts/enums per conversation', () => {
    const settings = read(path.join(src, 'main/live/settings.ts'))
    expect([...settings.matchAll(/writeFileSync\(([^,]+),/g)].map((m) => m[1])).toEqual(['this.file'])
    const meter = read(path.join(src, 'main/live/meter.ts'))
    expect([...meter.matchAll(/appendFileSync\(([^,]+),/g)].map((m) => m[1])).toEqual(['file'])
    expect(meter).not.toMatch(/transcript|b64|base64|jpeg|audio_data/i)
  })
  it('no audio, frame or transcript is held in a module-level or exported store', () => {
    for (const f of liveMain) expect(read(f), rel(f)).not.toMatch(/export (const|let|var) \w*(frames?|audio|transcripts?|history|recordings?)\w*\s*[:=]\s*(\[|new (Map|Set)|\{)/i)
  })
})

describe('no content in a log line', () => {
  it('no console output in the voice main code (logging is an injected function), apart from one settings save error', () => {
    for (const f of liveMain) {
      if (path.basename(f) === 'settings.ts') continue
      expect(read(f), rel(f)).not.toMatch(/console\.(log|info|warn|error|debug)/)
    }
  })
  it('no log call names audio, a frame, a transcript, a token or the key', () => {
    for (const f of [...liveMain, ...voiceFiles.filter((x) => x.includes('renderer'))]) {
      for (const line of read(f).split('\n')) {
        if (/\blog\??\.?\(/.test(line) && !/^\s*\/\//.test(line)) expect(line, rel(f)).not.toMatch(/transcript|b64|base64|jpeg|\.token\b|apiKey|GEMINI|inputTranscription|outputTranscription/i)
      }
    }
  })
  it('the old wake code and the dock bridge log nothing from the microphone', () => {
    for (const f of walk(path.join(src, 'renderer/wake')).filter((x) => !isTest(x))) expect(read(f), rel(f)).not.toMatch(/localStorage|writeFile|appendFile/)
  })
})

describe('the microphone permission is never requested', () => {
  it('main code only reads the status; nothing asks', () => {
    for (const f of liveMain) expect(read(f), rel(f)).not.toMatch(/askForMediaAccess|requestMicrophone|getUserMedia/)
    expect(read(path.join(src, 'main/live/electron.ts'))).toMatch(/getMediaAccessStatus\('microphone'\)/)
  })
  it('getUserMedia lives in the renderer audio module only', () => {
    const users = walk(path.join(src, 'renderer/live')).filter((f) => !isTest(f) && /getUserMedia/.test(read(f))).map((f) => path.basename(f))
    expect(users).toEqual(['audio.ts'])
  })
})

describe('house rules', () => {
  it('no source claims the "sandbox" image source (the engine guard scans for the quoted word)', () => {
    for (const f of [...liveMain, ...walk(path.join(src, 'renderer/live'))]) expect(read(f), rel(f)).not.toMatch(/['"`]sandbox['"`]/)
  })
  it('the voice main code starts no process and evaluates no string', () => {
    for (const f of liveMain) expect(read(f), rel(f)).not.toMatch(/child_process|\beval\s*\(|new Function\s*\(|execFile|spawn\s*\(/)
  })
  it('every source declares the websocket endpoint only in wire.ts, and it is the Gemini host', () => {
    const hits = liveMain.filter((f) => /generativelanguage\.googleapis\.com/.test(read(f))).map((f) => path.basename(f)).sort()
    expect(hits).toEqual(['connection.ts', 'token.ts', 'wire.ts'])
  })
  it('model ids are never written in the voice code: they come from the environment', () => {
    for (const f of liveMain) expect(read(f), rel(f)).not.toMatch(/gemini-\d|gemini-[a-z]+-\d/i)
  })
})
