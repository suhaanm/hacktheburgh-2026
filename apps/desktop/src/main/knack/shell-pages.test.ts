import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_NAME, BRAND_ASSET_PATHS } from '../../shared/brand'
import { createAppHandler } from './app-protocol'
import { FAIL_MESSAGES } from './stack'
import { SLOW_START_MS, shellPages, startingText, uiStateOf } from './shell-pages'

const glyph = fs.readFileSync(path.resolve(__dirname, '../../../../..', BRAND_ASSET_PATHS.glyph), 'utf8')

describe('the Starting page', () => {
  it('says the product name and an ellipsis, at most three words', () => {
    expect(startingText(APP_NAME)).toBe('Starting Knack…')
    expect(startingText(APP_NAME).split(/\s+/).length).toBeLessThanOrEqual(3)
  })
  it('maps the lifecycle to what the page shows: starting, ready, or one plain error', () => {
    expect(uiStateOf({ phase: 'idle' }, APP_NAME)).toEqual({ kind: 'starting', text: 'Starting Knack…' })
    expect(uiStateOf({ phase: 'starting', step: 'agent' }, APP_NAME, 'Running with example data')).toEqual({ kind: 'starting', text: 'Starting Knack…', notice: 'Running with example data' })
    expect(uiStateOf({ phase: 'starting', step: 'engine' }, APP_NAME)).toEqual({ kind: 'starting', text: 'Starting Knack…' })
    expect(uiStateOf({ phase: 'ready', started: [], dashboard: 'dist', mock: null }, APP_NAME, 'Running with example data')).toEqual({ kind: 'ready' })
    expect(uiStateOf({ phase: 'failed', code: 'engine_failed', message: FAIL_MESSAGES.engine_failed, hint: 'See data/logs/knack-engine.log.' }, APP_NAME)).toEqual({ kind: 'error', message: 'The engine did not start.', hint: 'See data/logs/knack-engine.log.' })
  })
  it('has one button (Try again), no inline script or style, the brand glyph and no remote address', () => {
    const pages = shellPages({ appName: APP_NAME, glyphSvg: glyph })
    const html = pages['starting.html']!.body
    expect(html.match(/<button/g)).toHaveLength(1)
    expect(html).toContain('Try again')
    expect(html).toContain('Starting Knack…')
    expect(html).toContain('<svg')
    expect(html).toContain('currentColor')
    expect(html).not.toMatch(/<script>|<script [^>]*>[^<]|style=|https?:/)
    expect(pages['starting.js']!.body).not.toMatch(/https?:|eval\(/)
    expect(pages['starting.css']!.body).toContain('prefers-color-scheme: dark')
    expect(pages['starting.css']!.body).toContain('prefers-reduced-motion')
  })
  it('is served by the app protocol under /__shell/, with the policy', async () => {
    const handler = createAppHandler({ distRoot: null, ports: { engine: 1, agent: 2, dashboard: 3 }, token: () => null, shellAssets: shellPages({ appName: APP_NAME, glyphSvg: glyph }) })
    for (const f of ['starting.html', 'starting.css', 'starting.js']) {
      const res = await handler(new Request(`app://knack/__shell/${f}`))
      expect(res.status, f).toBe(200)
      expect(res.headers.get('content-security-policy')).toContain("script-src 'self'")
    }
  })
})

describe('a slow start', () => {
  it('after thirty seconds the page says it is still starting, in the same one line, and keeps the example data notice', () => {
    expect(uiStateOf({ phase: 'starting', step: 'engine' }, 'Knack', 'Running with example data')).toEqual({ kind: 'starting', text: 'Starting Knack…', notice: 'Running with example data' })
    expect(uiStateOf({ phase: 'starting', step: 'engine' }, 'Knack', 'Running with example data', true)).toEqual({ kind: 'starting', text: 'Still starting Knack…', notice: 'Running with example data' })
    expect(SLOW_START_MS).toBe(30_000)
  })
  it('a ready or failed stack is never "slow"', () => {
    expect(uiStateOf({ phase: 'ready', started: [], dashboard: 'dist', mock: null }, 'Knack', null, true)).toEqual({ kind: 'ready' })
    expect(uiStateOf({ phase: 'failed', code: 'port_busy', message: 'Another program is using a port Knack needs.' }, 'Knack', null, true)).toMatchObject({ kind: 'error' })
  })
})
