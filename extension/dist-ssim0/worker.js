"use strict";
(() => {
  // src/shared/types.ts
  var EVENT_TYPES = [
    "nav",
    "click",
    "scroll",
    "focus",
    "tab",
    "copy",
    "paste",
    "search",
    "idle",
    "lock",
    "unlock",
    "sleep",
    "resume",
    "stuck",
    "coach_shown",
    "coach_followed",
    "coach_dismissed",
    "agent_step",
    "approval",
    "undo",
    "task_start",
    "task_end",
    "progress"
  ];
  var DEFAULT_CONFIG = {
    capturing: false,
    // opt-in: nothing is captured until the worker turns it on (PR3)
    person: "",
    role: "benefits-processor",
    engine_url: "http://127.0.0.1:7700",
    desktop_url: "http://127.0.0.1:7720",
    identity_adopted: false
  };
  var STORAGE_KEYS = {
    config: "config",
    salt: "salt",
    queue: "queue",
    task: "task",
    l1Targets: "l1_targets",
    stats: "stats"
  };

  // src/shared/events.ts
  var PERSON_RE = /^p_[a-z0-9]{2,16}$/;
  var ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/;
  var TARGET_ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/;
  var LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/;
  var DOMAIN_HASH_RE = /^d:[0-9a-f]{4,16}$/;
  var META_KEY_RE = /^[a-z][a-z0-9_]{0,31}$/;
  var META_STR_RE = /^[a-z0-9_:\-.]{0,32}$/;
  var TASK_RE = /^t_[A-Za-z0-9_-]{1,32}$/;
  var ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
  var KNOWN_KEYS = /* @__PURE__ */ new Set(["schema", "id", "t", "origin", "actor", "person", "role", "source", "type", "target", "task_id", "meta"]);
  function validateMeta(meta) {
    if (meta === void 0) return null;
    const keys = Object.keys(meta);
    if (keys.length > 16) return "meta has more than 16 keys";
    for (const k of keys) {
      if (!META_KEY_RE.test(k)) return `meta key ${JSON.stringify(k)} is not allowed`;
      const v = meta[k];
      if (typeof v === "number") {
        if (!Number.isFinite(v)) return `meta.${k} is not finite`;
      } else if (typeof v === "string") {
        if (!META_STR_RE.test(v)) return `meta.${k} is not a short enum token`;
      } else if (typeof v !== "boolean") return `meta.${k} has a disallowed type`;
    }
    return null;
  }
  function validateEvent(e) {
    if (typeof e !== "object" || e === null) return "not an object";
    const ev = e;
    for (const k of Object.keys(ev)) if (!KNOWN_KEYS.has(k)) return `unknown key ${k}`;
    if (ev.schema !== 1) return "schema must be 1";
    if (typeof ev.id !== "string" || ev.id.length < 8 || ev.id.length > 64) return "bad id";
    if (typeof ev.t !== "string" || !ISO_RE.test(ev.t)) return "bad t";
    if (ev.origin !== "real" && ev.origin !== "synthetic") return "bad origin";
    if (ev.actor !== "human" && ev.actor !== "agent") return "bad actor";
    if (typeof ev.person !== "string" || !PERSON_RE.test(ev.person)) return "bad person";
    if (typeof ev.role !== "string" || !ROLE_RE.test(ev.role)) return "bad role";
    if (!["browser", "screen", "os", "desk", "agent", "coach"].includes(ev.source)) return "bad source";
    if (!EVENT_TYPES.includes(ev.type)) return "bad type";
    if (ev.task_id !== void 0 && (typeof ev.task_id !== "string" || !TASK_RE.test(ev.task_id))) return "bad task_id";
    if (ev.target !== void 0) {
      const t = ev.target;
      if (typeof t !== "object" || t === null) return "bad target";
      for (const k of Object.keys(t)) if (!["role", "label_hash", "domain_hash"].includes(k)) return `unknown target key ${k}`;
      if (t.role !== void 0 && (typeof t.role !== "string" || !TARGET_ROLE_RE.test(t.role))) return "bad target.role";
      if (t.label_hash !== void 0 && (typeof t.label_hash !== "string" || !LABEL_HASH_RE.test(t.label_hash))) return "bad target.label_hash";
      if (t.domain_hash !== void 0 && (typeof t.domain_hash !== "string" || !DOMAIN_HASH_RE.test(t.domain_hash))) return "bad target.domain_hash";
    }
    return validateMeta(ev.meta);
  }
  function defaultUuid() {
    const c = globalThis.crypto;
    if (c?.randomUUID) return c.randomUUID();
    const b = new Uint8Array(16);
    if (c?.getRandomValues) c.getRandomValues(b);
    else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
    b[6] = b[6] & 15 | 64;
    b[8] = b[8] & 63 | 128;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, "0"));
    return `${h.slice(0, 4).join("")}-${h.slice(4, 6).join("")}-${h.slice(6, 8).join("")}-${h.slice(8, 10).join("")}-${h.slice(10).join("")}`;
  }
  function makeEvent(rec, cfg, deps, taskId) {
    const ev = {
      schema: 1,
      id: deps.uuid(),
      t: new Date(deps.now()).toISOString(),
      origin: "real",
      actor: "human",
      person: cfg.person,
      role: cfg.role,
      source: "browser",
      type: rec.type
    };
    if (taskId) ev.task_id = taskId;
    if (rec.target && Object.keys(rec.target).length) ev.target = { ...rec.target };
    if (rec.meta && Object.keys(rec.meta).length) ev.meta = { ...rec.meta };
    return validateEvent(ev) === null ? ev : null;
  }

  // src/shared/hash.ts
  var K = new Uint32Array([
    1116352408,
    1899447441,
    3049323471,
    3921009573,
    961987163,
    1508970993,
    2453635748,
    2870763221,
    3624381080,
    310598401,
    607225278,
    1426881987,
    1925078388,
    2162078206,
    2614888103,
    3248222580,
    3835390401,
    4022224774,
    264347078,
    604807628,
    770255983,
    1249150122,
    1555081692,
    1996064986,
    2554220882,
    2821834349,
    2952996808,
    3210313671,
    3336571891,
    3584528711,
    113926993,
    338241895,
    666307205,
    773529912,
    1294757372,
    1396182291,
    1695183700,
    1986661051,
    2177026350,
    2456956037,
    2730485921,
    2820302411,
    3259730800,
    3345764771,
    3516065817,
    3600352804,
    4094571909,
    275423344,
    430227734,
    506948616,
    659060556,
    883997877,
    958139571,
    1322822218,
    1537002063,
    1747873779,
    1955562222,
    2024104815,
    2227730452,
    2361852424,
    2428436474,
    2756734187,
    3204031479,
    3329325298
  ]);
  function randomHex(bytes, cryptoLike = globalThis.crypto) {
    const buf = new Uint8Array(bytes);
    if (cryptoLike?.getRandomValues) cryptoLike.getRandomValues(buf);
    else for (let i = 0; i < bytes; i++) buf[i] = Math.floor(Math.random() * 256);
    return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // src/shared/config.ts
  var PERSON_RE2 = /^p_[a-z0-9]{2,16}$/;
  var ROLE_RE2 = /^[a-z][a-z0-9-]{1,40}$/;
  function parseIdentity(raw) {
    if (typeof raw !== "object" || raw === null) return null;
    const r = raw;
    if (typeof r.person !== "string" || !PERSON_RE2.test(r.person)) return null;
    if (typeof r.role !== "string" || !ROLE_RE2.test(r.role)) return null;
    return { person: r.person, role: r.role };
  }
  function newPersonId() {
    return `p_${randomHex(4)}`;
  }
  function cleanUrl(v, fallback) {
    if (typeof v !== "string") return fallback;
    try {
      const u = new URL(v);
      if (u.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(u.hostname)) return fallback;
      return `${u.protocol}//${u.host}`;
    } catch {
      return fallback;
    }
  }
  function normaliseConfig(raw) {
    const r = typeof raw === "object" && raw !== null ? raw : {};
    return {
      capturing: r.capturing === true,
      person: typeof r.person === "string" && PERSON_RE2.test(r.person) ? r.person : "",
      role: typeof r.role === "string" && ROLE_RE2.test(r.role) ? r.role : DEFAULT_CONFIG.role,
      engine_url: cleanUrl(r.engine_url, DEFAULT_CONFIG.engine_url),
      desktop_url: cleanUrl(r.desktop_url, DEFAULT_CONFIG.desktop_url),
      identity_adopted: r.identity_adopted === true
    };
  }
  async function loadConfig(area) {
    const got = await area.get(STORAGE_KEYS.config);
    return normaliseConfig(got[STORAGE_KEYS.config]);
  }
  async function ensureConfig(area) {
    const cfg = await loadConfig(area);
    if (!cfg.person) {
      const latest = await loadConfig(area);
      latest.person = latest.person || newPersonId();
      await area.set({ [STORAGE_KEYS.config]: latest });
      return latest;
    }
    return cfg;
  }
  async function ensureSalt(area) {
    const got = await area.get(STORAGE_KEYS.salt);
    const existing = got[STORAGE_KEYS.salt];
    if (typeof existing === "string" && /^[0-9a-f]{32}$/.test(existing)) return existing;
    const salt = randomHex(16);
    await area.set({ [STORAGE_KEYS.salt]: salt });
    return salt;
  }

  // src/background/engine_client.ts
  var DEFAULT_OPTS = { maxBatch: 25, flushMs: 2e3, maxQueue: 1e3, backoffMaxMs: 6e4 };
  var Batcher = class {
    constructor(deps, opts = {}) {
      this.deps = deps;
      this.opts = { ...DEFAULT_OPTS, ...opts };
    }
    deps;
    queue = [];
    loaded = false;
    timer = null;
    flushing = null;
    fails = 0;
    notBefore = 0;
    stats = { accepted: 0, rejected: 0, dropped: 0, last_error: null, last_ok_at: null };
    opts;
    async ensureLoaded() {
      if (this.loaded) return;
      this.loaded = true;
      const stored = await this.deps.load();
      this.queue = [...stored, ...this.queue].slice(-this.opts.maxQueue);
    }
    size() {
      return this.queue.length;
    }
    async add(ev) {
      await this.ensureLoaded();
      this.queue.push(ev);
      if (this.queue.length > this.opts.maxQueue) {
        const over = this.queue.length - this.opts.maxQueue;
        this.queue.splice(0, over);
        this.stats.dropped += over;
      }
      await this.deps.save(this.queue);
      if (this.queue.length >= this.opts.maxBatch) void this.flush();
      else this.schedule(this.opts.flushMs);
    }
    /** The engine's identity replaced ours: unsent events join the engine's person instead of staying orphaned. */
    async retag(person, role) {
      await this.ensureLoaded();
      for (const ev of this.queue) {
        ev.person = person;
        ev.role = role;
      }
      await this.deps.save(this.queue);
    }
    /** Consent revoked: forget everything not yet sent. */
    async clear() {
      await this.ensureLoaded();
      this.queue = [];
      if (this.timer !== null) this.deps.clearTimer(this.timer);
      this.timer = null;
      await this.deps.save([]);
    }
    schedule(ms) {
      if (this.timer !== null) return;
      this.timer = this.deps.setTimer(() => {
        this.timer = null;
        void this.flush();
      }, ms);
    }
    flush() {
      if (this.flushing) return this.flushing;
      this.flushing = this.doFlush().finally(() => {
        this.flushing = null;
      });
      return this.flushing;
    }
    async doFlush() {
      await this.ensureLoaded();
      while (this.queue.length) {
        const wait = this.notBefore - this.deps.now();
        if (wait > 0) {
          this.schedule(wait);
          return;
        }
        const batch = this.queue.slice(0, this.opts.maxBatch);
        let status = 0;
        let body = null;
        try {
          const res = await this.deps.fetch(`${await this.deps.getUrl()}/events`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(batch)
          });
          status = res.status;
          if (res.ok) body = await res.json().catch(() => null);
        } catch (e) {
          this.fail(`network: ${e.message ?? "error"}`);
          return;
        }
        if (status >= 200 && status < 300) {
          const b = body ?? {};
          this.stats.accepted += typeof b.accepted === "number" ? b.accepted : batch.length;
          this.stats.rejected += Array.isArray(b.rejected) ? b.rejected.length : 0;
          this.stats.last_error = null;
          this.stats.last_ok_at = new Date(this.deps.now()).toISOString();
          this.fails = 0;
          this.notBefore = 0;
          this.queue.splice(0, batch.length);
          await this.deps.save(this.queue);
          this.deps.onStats?.({ ...this.stats });
        } else if (status >= 400 && status < 500) {
          this.stats.dropped += batch.length;
          this.stats.last_error = `engine answered ${status}`;
          this.queue.splice(0, batch.length);
          await this.deps.save(this.queue);
          this.deps.onStats?.({ ...this.stats });
        } else {
          this.fail(`engine answered ${status}`);
          return;
        }
      }
    }
    fail(msg) {
      this.fails += 1;
      this.stats.last_error = msg;
      const wait = Math.min(this.opts.backoffMaxMs, 1e3 * 2 ** Math.min(this.fails, 10));
      this.notBefore = this.deps.now() + wait;
      this.deps.onStats?.({ ...this.stats });
      this.schedule(wait);
    }
  };

  // src/background/consent.ts
  var OPTED_IN = /* @__PURE__ */ new Set(["shadow", "approval", "unattended"]);
  var ID_RE = /^[a-z][a-z0-9-]{2,40}$/;
  function l1Targets(payload) {
    const list = Array.isArray(payload) ? payload : typeof payload === "object" && payload !== null && Array.isArray(payload.data) ? payload.data : [];
    const out = [];
    for (const r of list) {
      if (typeof r !== "object" || r === null) continue;
      const id = typeof r.id === "string" && ID_RE.test(r.id) ? r.id : null;
      const mode = r.consent && typeof r.consent === "object" ? r.consent.mode : void 0;
      const status = typeof r.status === "string" ? r.status : "";
      if (id && typeof mode === "string" && OPTED_IN.has(mode) && status !== "declined" && status !== "never") out.push(id);
    }
    return [...new Set(out)].sort();
  }
  async function pollConsent(fetchFn, engineUrl) {
    try {
      const res = await fetchFn(`${engineUrl}/routines`, { method: "GET", headers: { accept: "application/json" } });
      if (!res.ok) return null;
      return l1Targets(await res.json());
    } catch {
      return null;
    }
  }

  // src/background/recording.ts
  var MAX_BUFFER = 300;
  var RETRY_MS = 5 * 6e4;
  var RecordingUploader = class {
    constructor(deps) {
      this.deps = deps;
      this.recordingId = `rec_${deps.uuid().replace(/-/g, "").slice(0, 12)}`;
    }
    deps;
    buffer = [];
    skipped = 0;
    recordingId;
    retryAt = 0;
    lastStatus = 0;
    size() {
      return this.buffer.length;
    }
    addStep(step) {
      if (!this.deps.getTargets().length) return;
      this.buffer.push(step);
      if (this.buffer.length > MAX_BUFFER) this.buffer.splice(0, this.buffer.length - MAX_BUFFER);
    }
    addSkipped(n = 1) {
      this.skipped += n;
    }
    clear() {
      this.buffer = [];
      this.skipped = 0;
    }
    async flush() {
      const targets = this.deps.getTargets();
      if (!targets.length || !this.buffer.length && !this.skipped) return;
      if (this.deps.now() < this.retryAt) return;
      const { person, role } = this.deps.identity();
      const steps = this.buffer.slice();
      const skipped = this.skipped;
      let delivered = true;
      for (const id of targets) {
        try {
          const res = await this.deps.fetch(`${await this.deps.getUrl()}/routines/${id}/recording`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ schema: 1, routine_id: id, recording_id: this.recordingId, role, person, steps, skipped_sensitive: skipped })
          });
          this.lastStatus = res.status;
          if (res.status === 404 || res.status === 405 || res.status >= 500) {
            delivered = false;
            this.retryAt = this.deps.now() + RETRY_MS;
          }
        } catch {
          delivered = false;
          this.retryAt = this.deps.now() + 15e3;
        }
      }
      if (delivered) {
        this.buffer.splice(0, steps.length);
        this.skipped = Math.max(0, this.skipped - skipped);
      }
    }
  };

  // src/background/rect_poller.ts
  var REQUEST_ID_RE = /^[A-Za-z0-9_.:-]{1,64}$/;
  var FRAME_RE = /^(top|f[0-9]{1,4})$/;
  var LABEL_HASH_RE2 = /^h:[0-9a-f]{4,16}$/;
  var ROLE_RE3 = /^[a-z][a-z0-9_-]{0,31}$/;
  var ZONE_RE = /^[a-z][a-z0-9_]{1,30}$/;
  function parseWant(raw) {
    if (typeof raw !== "object" || raw === null) return null;
    const r = raw;
    if (typeof r.request_id !== "string" || !REQUEST_ID_RE.test(r.request_id)) return null;
    if (typeof r.frame_id !== "string" || !FRAME_RE.test(r.frame_id)) return null;
    const want = { request_id: r.request_id, frame_id: r.frame_id };
    const none = (...ks) => ks.every((k) => r[k] === void 0);
    if (typeof r.label_hash === "string" && LABEL_HASH_RE2.test(r.label_hash) && none("role", "name", "zone")) {
      want.label_hash = r.label_hash;
    } else if (typeof r.role === "string" && ROLE_RE3.test(r.role) && typeof r.name === "string" && r.name.length > 0 && r.name.length <= 80 && none("label_hash", "zone")) {
      want.role = r.role;
      want.name = r.name;
    } else if (typeof r.zone === "string" && ZONE_RE.test(r.zone) && none("label_hash", "role", "name")) {
      want.zone = r.zone;
    } else return null;
    return want;
  }
  var RectPoller = class {
    constructor(deps) {
      this.deps = deps;
    }
    deps;
    failures = 0;
    async tick() {
      const base = await this.deps.getDesktopUrl();
      let res;
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 1500);
      try {
        res = await this.deps.fetch(`${base}/ext/want`, { method: "GET", headers: { accept: "application/json" }, signal: ctl.signal });
      } catch {
        this.failures += 1;
        return { delay: Math.min(3e4, 2e3 * 2 ** Math.min(this.failures, 4)), reachable: false, answered: false };
      } finally {
        clearTimeout(timer);
      }
      this.failures = 0;
      if (res.status === 204) return { delay: 400, reachable: true, answered: false };
      if (!res.ok) return { delay: 2e3, reachable: true, answered: false };
      const want = parseWant(await res.json().catch(() => null));
      if (!want) return { delay: 400, reachable: true, answered: false };
      const found = await this.deps.resolve(want).catch(() => null);
      const body = found && found.found ? { request_id: want.request_id, frame_id: found.frame_id, found: true, rect: found.rect, window_offset: found.window_offset, scroll: found.scroll, dpr: found.dpr, viewport: found.viewport, outer: found.outer, screen: found.screen, age_ms: Math.max(0, this.deps.now() - found.measured_at) } : { request_id: want.request_id, frame_id: want.frame_id, found: false, age_ms: 0 };
      try {
        await this.deps.fetch(`${base}/ext/rect`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      } catch {
      }
      return { delay: 0, reachable: true, answered: true };
    }
  };

  // src/background/worker_core.ts
  var STALE_TASK_MS = 10 * 6e4;
  var PROGRESS_MIN_GAP_MS = 5e3;
  var TASK_PERSIST_MS = 5e3;
  function createWorker(api2, deps) {
    const uuid = deps.uuid ?? defaultUuid;
    let cfg = { ...DEFAULT_CONFIG };
    let salt = "";
    let l1TargetIds = [];
    let l1Timer = null;
    let rectPromise = null;
    let task = null;
    let taskPersistedAt = 0;
    let stampAt = 0;
    const lastProgress = /* @__PURE__ */ new Map();
    const newTaskId = deps.taskId ?? (() => `t_${randomHex(6)}`);
    let rectReachable = false;
    const batcher = new Batcher({
      fetch: deps.fetch,
      getUrl: async () => cfg.engine_url,
      load: async () => (await api2.storage.get(STORAGE_KEYS.queue))[STORAGE_KEYS.queue] ?? [],
      save: (q) => api2.storage.set({ [STORAGE_KEYS.queue]: q }),
      setTimer: deps.setTimer,
      clearTimer: deps.clearTimer,
      now: deps.now,
      onStats: (s) => void api2.storage.set({ [STORAGE_KEYS.stats]: s })
    });
    const uploader = new RecordingUploader({
      fetch: deps.fetch,
      getUrl: async () => cfg.engine_url,
      getTargets: () => cfg.capturing ? l1TargetIds : [],
      identity: () => ({ person: cfg.person, role: cfg.role }),
      now: deps.now,
      uuid
    });
    const poller = new RectPoller({
      fetch: deps.fetch,
      getDesktopUrl: async () => cfg.desktop_url,
      now: deps.now,
      resolve: async (want) => {
        if (!cfg.capturing) return null;
        const tab = await api2.queryActiveTab();
        if (!tab) return null;
        const first = want.frame_id === "top" ? 0 : Number(want.frame_id.slice(1));
        const order = [first, ...await api2.getFrameIds(tab.id).catch(() => [])].filter((f, i, a) => a.indexOf(f) === i);
        for (const fid of order) {
          const r = await api2.sendToTab(tab.id, { kind: "rect", want }, fid).catch(() => null);
          if (r && r.found) return { ...r, frame_id: fid === 0 ? "top" : `f${fid}` };
        }
        return null;
      }
    });
    async function init() {
      cfg = await ensureConfig(api2.storage);
      salt = await ensureSalt(api2.storage);
      const got = await api2.storage.get(STORAGE_KEYS.l1Targets);
      const ids = got[STORAGE_KEYS.l1Targets];
      l1TargetIds = Array.isArray(ids) ? ids.filter((x) => typeof x === "string") : [];
      const saved = (await api2.storage.get(STORAGE_KEYS.task))[STORAGE_KEYS.task];
      if (saved && typeof saved.id === "string" && /^t_[A-Za-z0-9_-]{1,32}$/.test(saved.id) && typeof saved.last_at === "number" && deps.now() - saved.last_at < STALE_TASK_MS) {
        task = { id: saved.id, lastAt: saved.last_at };
      }
      if (cfg.capturing) void startRect();
    }
    async function onConfigChanged(raw) {
      const was = cfg.capturing;
      cfg = normaliseConfig(raw);
      if (!cfg.person) cfg = await ensureConfig(api2.storage);
      if (was && !cfg.capturing) {
        await batcher.clear();
        uploader.clear();
        task = null;
        await api2.storage.remove(STORAGE_KEYS.task);
        await api2.storage.set({ [STORAGE_KEYS.l1Targets]: [] });
        l1TargetIds = [];
      }
      if (!was && cfg.capturing) {
        void refreshConsent();
        void startRect();
      }
    }
    function scheduleL1Flush() {
      if (l1Timer !== null) return;
      l1Timer = deps.setTimer(() => {
        l1Timer = null;
        void uploader.flush();
      }, 3e3);
    }
    function stamp() {
      stampAt = Math.max(deps.now(), stampAt + 1);
      return stampAt;
    }
    async function persistTask(force = false) {
      if (!task) return;
      const t = deps.now();
      if (!force && t - taskPersistedAt < TASK_PERSIST_MS) return;
      taskPersistedAt = t;
      await api2.storage.set({ [STORAGE_KEYS.task]: { id: task.id, last_at: task.lastAt } });
    }
    async function emitEvent(rec) {
      const at = stamp();
      const ev = makeEvent({ type: rec.type, target: rec.target, meta: rec.meta }, cfg, { now: () => at, uuid }, task?.id);
      if (!ev) return false;
      if (task) task.lastAt = at;
      await batcher.add(ev);
      return true;
    }
    async function handleRecord(rec) {
      const markers = rec.markers;
      const now = deps.now();
      if (task && now - task.lastAt >= STALE_TASK_MS) {
        task = null;
        await api2.storage.remove(STORAGE_KEYS.task);
      }
      if (markers?.start && (!task || now - task.lastAt >= markers.start.idle_s * 1e3)) {
        task = { id: newTaskId(), lastAt: now };
        taskPersistedAt = 0;
        await emitEvent({ type: "task_start", meta: rec.meta?.zone ? { zone: rec.meta.zone } : void 0 });
        await persistTask(true);
      }
      const ok = await emitEvent(rec);
      for (const kind of markers?.progress ?? []) {
        const key = `${task?.id ?? "-"}:${kind}`;
        if (now - (lastProgress.get(key) ?? -Infinity) < PROGRESS_MIN_GAP_MS) continue;
        lastProgress.set(key, now);
        await emitEvent({ type: "progress", meta: { kind } });
      }
      if (markers?.end && task) {
        await emitEvent({ type: "task_end", meta: { reason: markers.end.reason } });
        task = null;
        await api2.storage.remove(STORAGE_KEYS.task);
      } else {
        await persistTask();
      }
      return ok;
    }
    async function handleMessage(msg) {
      switch (msg?.kind) {
        case "record": {
          if (!cfg.capturing || !cfg.person) return { ok: false };
          return { ok: await handleRecord(msg.record) };
        }
        case "l1":
          if (cfg.capturing && l1TargetIds.length) {
            uploader.addStep(msg.step);
            scheduleL1Flush();
          }
          return { ok: true };
        case "l1_skipped":
          uploader.addSkipped();
          return { ok: true };
        case "get_salt":
          return { salt: salt || (salt = await ensureSalt(api2.storage)) };
        case "popup_status":
          return { config: cfg, stats: batcher.stats, queued: batcher.size(), l1_targets: l1TargetIds, l1_buffer: uploader.size(), desktop_reachable: rectReachable };
        default:
          return { ok: false };
      }
    }
    async function refreshIdentity() {
      let body = null;
      try {
        const res = await deps.fetch(`${cfg.engine_url}/identity`, { method: "GET", headers: { accept: "application/json" } });
        if (!res.ok) return;
        body = await res.json().catch(() => null);
      } catch {
        return;
      }
      const id = parseIdentity(body);
      if (!id) return;
      if (cfg.identity_adopted && cfg.person === id.person && cfg.role === id.role) return;
      cfg = { ...cfg, person: id.person, role: id.role, identity_adopted: true };
      await api2.storage.set({ [STORAGE_KEYS.config]: cfg });
      await batcher.retag(id.person, id.role);
    }
    async function onTabActivated(tabId) {
      if (!cfg.capturing) return;
      const info = await api2.sendToTab(tabId, { kind: "page_info" }, 0).catch(() => null);
      if (!info?.domain_hash) return;
      const record = { type: "tab", target: { role: "tab", domain_hash: info.domain_hash } };
      if (info.zone) record.meta = { zone: info.zone };
      await handleMessage({ kind: "record", record });
    }
    async function refreshConsent() {
      if (!cfg.capturing) return;
      await refreshIdentity();
      const ids = await pollConsent(deps.fetch, cfg.engine_url);
      if (ids === null) return;
      if (JSON.stringify(ids) !== JSON.stringify(l1TargetIds)) {
        l1TargetIds = ids;
        await api2.storage.set({ [STORAGE_KEYS.l1Targets]: ids });
      }
      if (!ids.length) uploader.clear();
    }
    async function onAlarm(name) {
      if (name === "tick") {
        await batcher.flush();
        await uploader.flush();
        await refreshConsent();
        if (cfg.capturing) void startRect();
      }
    }
    function startRect() {
      if (rectPromise) return rectPromise;
      rectPromise = (async () => {
        while (cfg.capturing) {
          const out = await poller.tick();
          rectReachable = out.reachable;
          if (out.reachable) api2.keepAlive();
          else if (out.delay >= 8e3) break;
          if (out.delay > 0) await deps.sleep(out.delay);
        }
      })().finally(() => {
        rectPromise = null;
      });
      return rectPromise;
    }
    return {
      init,
      handleMessage,
      onTabActivated,
      onConfigChanged,
      onAlarm,
      refreshConsent,
      refreshIdentity,
      startRect,
      batcher,
      uploader,
      poller,
      get task() {
        return task;
      },
      get config() {
        return cfg;
      },
      get l1Targets() {
        return l1TargetIds;
      }
    };
  }

  // src/background/worker.ts
  var api = {
    storage: chrome.storage.local,
    sendToTab: (tabId, msg, frameId) => chrome.tabs.sendMessage(tabId, msg, { frameId }).catch(() => null),
    queryActiveTab: async () => {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      return tab?.id !== void 0 ? { id: tab.id } : null;
    },
    getFrameIds: async (tabId) => {
      const frames = await chrome.webNavigation.getAllFrames({ tabId });
      return (frames ?? []).map((f) => f.frameId);
    },
    keepAlive: () => void chrome.runtime.getPlatformInfo(() => void 0)
  };
  var worker = createWorker(api, {
    fetch: (...a) => fetch(...a),
    now: () => Date.now(),
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: (h) => clearTimeout(h),
    sleep: (ms) => new Promise((r) => setTimeout(r, ms))
  });
  var ready = worker.init();
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id) return false;
    ready.then(() => worker.handleMessage(msg)).then(sendResponse, () => sendResponse({ ok: false }));
    return true;
  });
  chrome.tabs.onActivated.addListener((info) => {
    void ready.then(() => worker.onTabActivated(info.tabId));
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes[STORAGE_KEYS.config]) void ready.then(() => worker.onConfigChanged(changes[STORAGE_KEYS.config]?.newValue));
  });
  chrome.alarms.create("tick", { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener((a) => void ready.then(() => worker.onAlarm(a.name)));
  chrome.runtime.onInstalled.addListener(() => void ready);
})();
