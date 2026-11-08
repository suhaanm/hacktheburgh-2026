// The real dependencies of the services lifecycle (stack.ts): HTTP on loopback, child processes in their own process groups, files.
// Not unit-tested (the lifecycle is, with fakes); exercised by the hidden check (scripts/knack-check) against stand-in servers.
import { spawn as nodeSpawn, type ChildProcess } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { augmentedPath, createStack, type ChildHandle, type SpawnSpec, type Stack, type StackConfig, type StackDeps } from './stack'

/** GET on 127.0.0.1 only (the address is built from a port, never from text). A 2xx answer within the limit is ok. */
export function loopbackGet(url: string, timeoutMs: number): Promise<{ ok: boolean; json?: unknown }> {
  return new Promise((resolve) => {
    let u: URL
    try {
      u = new URL(url)
    } catch {
      resolve({ ok: false })
      return
    }
    if (u.hostname !== '127.0.0.1') {
      resolve({ ok: false })
      return
    }
    const req = http.get({ host: '127.0.0.1', port: Number(u.port), path: `${u.pathname}${u.search}`, agent: false, timeout: timeoutMs }, (res) => {
      const chunks: Buffer[] = []
      let size = 0
      res.on('data', (c: Buffer) => {
        size += c.length
        if (size < 256 * 1024) chunks.push(c)
      })
      res.on('end', () => {
        const ok = (res.statusCode ?? 0) >= 200 && (res.statusCode ?? 0) < 300
        let json: unknown
        try {
          json = JSON.parse(Buffer.concat(chunks).toString('utf8'))
        } catch {
          json = undefined
        }
        resolve({ ok, json })
      })
      res.on('error', () => resolve({ ok: false }))
    })
    req.on('timeout', () => req.destroy())
    req.on('error', () => resolve({ ok: false }))
  })
}

function openLog(file: string): number | 'ignore' {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true })
    return fs.openSync(file, 'a')
  } catch {
    return 'ignore'
  }
}

function wrap(child: ChildProcess): ChildHandle {
  const exited = new Promise<number | null>((resolve) => {
    child.once('exit', (code) => resolve(code))
    child.once('error', () => resolve(1))
  })
  return {
    pid: child.pid ?? null,
    exited,
    kill(signal) {
      // The child leads its own group (detached), so a negative pid reaches `uv` and the python it started.
      try {
        if (child.pid) process.kill(-child.pid, signal)
      } catch {
        try {
          child.kill(signal)
        } catch {
          /* already gone */
        }
      }
    },
  }
}

export const dataDirId = (dir: string): string | null => {
  try {
    return crypto.createHash('sha256').update(fs.realpathSync(dir)).digest('hex').slice(0, 12)
  } catch {
    return null
  }
}

export function findExecutable(name: string, env: NodeJS.ProcessEnv = process.env): string | null {
  for (const dir of augmentedPath(env.PATH, env.HOME ?? '').split(':')) {
    const file = path.join(dir, name)
    try {
      fs.accessSync(file, fs.constants.X_OK)
      if (fs.statSync(file).isFile()) return file
    } catch {
      /* not here */
    }
  }
  return null
}

/** Something accepts connections on this port of this machine (a quick connect, then gone). */
export function loopbackPortBusy(port: number, timeoutMs = 400): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port })
    const done = (busy: boolean): void => {
      socket.destroy()
      resolve(busy)
    }
    socket.setTimeout(timeoutMs, () => done(false))
    socket.once('connect', () => done(true))
    socket.once('error', () => done(false))
  })
}

export function realStackDeps(config: StackConfig, log?: (...args: unknown[]) => void): StackDeps {
  const logPath = (name: string): string => path.join(config.repoRoot ?? process.cwd(), 'data', 'logs', `knack-${name}.log`)
  return {
    config,
    get: loopbackGet,
    portBusy: (port) => loopbackPortBusy(port),
    spawn(spec: SpawnSpec) {
      const fd = openLog(logPath(spec.name))
      const child = nodeSpawn(spec.command, spec.args, { cwd: spec.cwd, env: spec.env, detached: true, stdio: ['ignore', fd, fd] })
      if (typeof fd === 'number') fs.closeSync(fd)
      return wrap(child)
    },
    run(spec, timeoutMs) {
      return new Promise((resolve) => {
        const fd = openLog(logPath(spec.name))
        const child = nodeSpawn(spec.command, spec.args, { cwd: spec.cwd, env: spec.env, stdio: ['ignore', fd, fd] })
        if (typeof fd === 'number') fs.closeSync(fd)
        const timer = setTimeout(() => child.kill('SIGKILL'), timeoutMs)
        child.once('exit', (code) => {
          clearTimeout(timer)
          resolve({ code })
        })
        child.once('error', () => {
          clearTimeout(timer)
          resolve({ code: 1 })
        })
      })
    },
    exists: (p) => fs.existsSync(p),
    mkdirp: (p) => void fs.mkdirSync(p, { recursive: true }),
    touch: (p) => {
      try {
        fs.mkdirSync(path.dirname(p), { recursive: true })
        fs.closeSync(fs.openSync(p, 'a'))
      } catch {
        /* a marker that cannot be written is only a missing marker */
      }
    },
    findExecutable: (name) => findExecutable(name),
    env: () => Object.fromEntries(Object.entries(process.env).filter((e): e is [string, string] => typeof e[1] === 'string')),
    dataDirId,
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    now: () => Date.now(),
    log,
  }
}

export const createRealStack = (config: StackConfig, log?: (...args: unknown[]) => void): Stack => createStack(realStackDeps(config, log))
