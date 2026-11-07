import http from 'node:http'
import { describe, expect, it } from 'vitest'
import { liveServiceProblem } from './no-live-services'

describe('the guard that keeps unit tests off the live dev stack', () => {
  it('recognises the live ports on every loopback spelling, and nothing else', () => {
    for (const u of ['http://127.0.0.1:7700/kill', 'http://localhost:7710/health', 'http://[::1]:7700/x', 'http://127.0.0.1:5173/', 'http://127.0.0.1:7801/__reset']) expect(liveServiceProblem(u), u).toMatch(/live dev service/)
    expect(liveServiceProblem({ hostname: '127.0.0.1', port: 7710 })).toMatch(/live dev service/)
    for (const u of ['http://127.0.0.1:58426/kill', 'http://example.com:7700/', 'http://127.0.0.1:9/']) expect(liveServiceProblem(u), u).toBeNull()
  })

  it('fetch and node:http refuse a live port before anything is sent', async () => {
    await expect(fetch('http://127.0.0.1:7700/kill', { method: 'POST' })).rejects.toThrow(/live dev service/)
    await expect(fetch('http://127.0.0.1:7710/kill', { method: 'POST' })).rejects.toThrow(/live dev service/)
    expect(() => http.request({ hostname: '127.0.0.1', port: 7700, method: 'POST', path: '/kill' })).toThrow(/live dev service/)
    expect(() => http.get('http://127.0.0.1:7710/health')).toThrow(/live dev service/)
  })

  it('every test has a private data directory, never <repo>/data', () => {
    expect(process.env.UNDERSTUDY_DATA_DIR).toMatch(/understudy-test-data/)
  })
})
