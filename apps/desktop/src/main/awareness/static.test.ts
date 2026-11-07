// Static checks over the awareness sources (test files and test utilities excluded): the rules that cannot be shown by running one path.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const dir = __dirname
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.ts') && !f.endsWith('.test.ts') && !f.endsWith('.test-util.ts'))
const text = (f: string): string => fs.readFileSync(path.join(dir, f), 'utf8')
// Code only: whole-line comments are dropped, so a comment may NAME a thing the code must not do.
const code = (f: string): string => text(f).split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')

describe('awareness sources', () => {
  it('there are sources to check', () => expect(files.length).toBeGreaterThan(12))

  it('no source claims the "sandbox" image source (real-screen code; the engine guard scans for the quoted word)', () => {
    for (const f of files) expect(text(f), f).not.toMatch(/['"`]sandbox['"`]/)
  })

  it('nothing names a model provider host or SDK: frames reach a provider only through the engine guard', () => {
    for (const f of files) expect(text(f), f).not.toMatch(/generativelanguage\.googleapis|@google\/genai|api\.openai\.com|aiplatform\.googleapis|openai|anthropic/i)
  })

  it('only the settings store writes to disk (small JSON, never a frame); no source writes or caches an image', () => {
    const writers = files.filter((f) => /\b(writeFile|writeFileSync|appendFile|appendFileSync|createWriteStream|writeSync|copyFile|rename)\b/.test(text(f)))
    expect(writers).toEqual(['settings.ts'])
    for (const f of files) expect(text(f), f).not.toMatch(/tmpdir|mkdtemp|os\.tmp|localStorage|IndexedDB/)
  })

  it('no source logs a frame, a body or a base64 string', () => {
    for (const f of files) {
      const logs = text(f).split('\n').filter((l) => /console\.(log|info|warn|error|debug)\(|\blog\(/.test(l))
      for (const l of logs) expect(l, `${f}: ${l.trim()}`).not.toMatch(/jpeg|frame|b64|base64|body/i)
    }
  })

  it('no source requests a macOS permission or installs an event tap', () => {
    for (const f of files) {
      expect(code(f), f).not.toMatch(/isTrustedAccessibilityClient\(\s*true|askForMediaAccess|requestScreen|CGEventTap|iohook|uiohook|globalShortcut\.register|desktopCapturer\.getSources/)
    }
  })

  it('the only network calls go to loopback: every fetch sits behind an isLoopback check', () => {
    for (const f of files.filter((x) => /\bfetch\(/.test(text(x)))) {
      expect(text(f), f).toMatch(/isLoopback/)
    }
  })
})
