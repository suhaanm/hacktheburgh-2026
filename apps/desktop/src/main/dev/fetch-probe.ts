// Wraps globalThis.fetch for Google API hosts: logs shape-only facts about each request (no headers, no key, no
// payload text) and optionally injects failures. Lets QA test failure handling of the REAL services at the boundary.
export interface FaultSpec {
  // Substring of the request path (model id such as "argon" or "flash"), or "*" for every Google API call.
  match: string
  mode: 'off' | 'timeout' | 'http500' | 'http429' | 'http401' | 'network' | 'garbage' | 'empty' | 'slow'
  // Number of calls to fault before the fault switches itself off; default unlimited.
  count?: number
  // For mode "slow": delay before passing the request through.
  delayMs?: number
}

export interface FetchLogEntry {
  t: number
  host: string
  path: string
  method: string
  model: string | null
  status: number | 'fault' | 'error'
  ms: number
  bodyKeys: string[]
  store: boolean | null
  hasImage: boolean
  bodyBytes: number
  faulted?: FaultSpec['mode']
}

export interface FetchProbe {
  log: FetchLogEntry[]
  setFault(spec: FaultSpec): void
  getFault(): FaultSpec | null
}

const GOOGLE_HOST = /(^|\.)googleapis\.com$/

// The Google SDK passes a Request object (body inside), not (url, init.body); read either form without consuming it.
export async function readRequestBody(input: Request | URL | string, init?: RequestInit): Promise<string | undefined> {
  if (typeof init?.body === 'string') return init.body
  if (init?.body instanceof Uint8Array) return Buffer.from(init.body).toString('utf8')
  if (input instanceof Request && input.body !== null) {
    try {
      return await input.clone().text()
    } catch {
      return undefined
    }
  }
  return undefined
}

function describeBody(body: unknown): { keys: string[]; store: boolean | null; hasImage: boolean; bytes: number; model: string | null } {
  if (typeof body !== 'string') return { keys: [], store: null, hasImage: false, bytes: 0, model: null }
  const bytes = Buffer.byteLength(body)
  try {
    const json = JSON.parse(body) as Record<string, unknown>
    const store = typeof json.store === 'boolean' ? json.store : null
    const model = typeof json.model === 'string' ? json.model.replace(/^models\//, '') : null
    return { keys: Object.keys(json), store, hasImage: /"mime_?[Tt]ype"\s*:\s*"image\//.test(body), bytes, model }
  } catch {
    return { keys: [], store: null, hasImage: false, bytes, model: null }
  }
}

export function installFetchProbe(): FetchProbe {
  const log: FetchLogEntry[] = []
  let fault: FaultSpec | null = null
  const realFetch = globalThis.fetch.bind(globalThis)

  globalThis.fetch = async (input: Request | URL | string, init?: RequestInit): Promise<Response> => {
    const raw = input instanceof Request ? input.url : String(input)
    let url: URL
    try {
      url = new URL(raw)
    } catch {
      return realFetch(input, init)
    }
    if (!GOOGLE_HOST.test(url.hostname)) return realFetch(input, init)

    const started = Date.now()
    const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
    const info = describeBody(await readRequestBody(input, init))
    // Generate-content puts the model in the path; the Interactions API puts it in the body.
    const model = /models\/([^/:?]+)/.exec(url.pathname)?.[1] ?? info.model
    const entry: FetchLogEntry = {
      t: started,
      host: url.hostname,
      path: url.pathname,
      method,
      model,
      status: 'error',
      ms: 0,
      bodyKeys: info.keys,
      store: info.store,
      hasImage: info.hasImage,
      bodyBytes: info.bytes,
    }
    log.push(entry)
    if (log.length > 2000) log.shift()

    const active = fault && fault.mode !== 'off' && (fault.match === '*' || url.pathname.includes(fault.match) || (model ?? '').includes(fault.match)) ? fault : null
    if (active) {
      if (active.count !== undefined) {
        active.count -= 1
        if (active.count <= 0) fault = null
      }
      entry.faulted = active.mode
      const done = (status: number | 'fault') => {
        entry.status = status
        entry.ms = Date.now() - started
      }
      const json = (status: number, body: unknown) => {
        done(status)
        return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
      }
      switch (active.mode) {
        case 'http500':
          return json(500, { error: { code: 500, message: 'Internal error encountered.', status: 'INTERNAL' } })
        case 'http429':
          return json(429, { error: { code: 429, message: 'Resource has been exhausted (e.g. check quota).', status: 'RESOURCE_EXHAUSTED' } })
        case 'http401':
          return json(401, { error: { code: 401, message: 'API key not valid. Please pass a valid API key.', status: 'UNAUTHENTICATED' } })
        case 'garbage':
          return json(200, {
            id: 'qa-fault',
            status: 'completed',
            steps: [{ type: 'model_output', content: [{ type: 'text', text: '<<<not json at all>>> ```{ "found": tru' }] }],
            candidates: [{ content: { parts: [{ text: '<<<not json at all>>> ```{ "found": tru' }] }, finishReason: 'STOP' }],
          })
        case 'empty':
          return json(200, { id: 'qa-fault', status: 'completed', steps: [], candidates: [] })
        case 'network':
          done('fault')
          throw new TypeError('fetch failed')
        case 'timeout': {
          // Hang until the caller aborts (a service with a sane timeout recovers); give up after 120 s.
          return new Promise<Response>((_, reject) => {
            const fail = (reason: string) => {
              done('fault')
              reject(new DOMException(reason, 'AbortError'))
            }
            const timer = setTimeout(() => fail('injected hang ended'), 120_000)
            init?.signal?.addEventListener('abort', () => {
              clearTimeout(timer)
              fail('The operation was aborted.')
            })
          })
        }
        case 'slow':
          await new Promise((r) => setTimeout(r, active.delayMs ?? 5000))
          break
        default:
          break
      }
    }

    try {
      const res = await realFetch(input, init)
      entry.status = res.status
      entry.ms = Date.now() - started
      return res
    } catch (err) {
      entry.status = 'error'
      entry.ms = Date.now() - started
      throw err
    }
  }

  return {
    log,
    setFault(spec) {
      fault = spec.mode === 'off' ? null : { ...spec }
    },
    getFault: () => fault,
  }
}
