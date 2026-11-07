/* Interactive preview. Globals annotationStyle, strokeLayers, LEVEL_NAMES, LEVEL_BLURBS, LEVEL_SUPPORT come from
   the real design modules (build.mjs inlines them), so this page cannot drift from the OVERLAY contract. */

// Placeholder personas: the only place names appear in this page.
const PERSONAS = {
  marcus: { displayName: 'Marcus', accentToken: 'accent-marcus' },
  amelia: { displayName: 'Amelia', accentToken: 'accent-amelia' },
};

const PHASES = {
  asleep: { name: 'Resting', blurb: 'Not listening. Say my name or press the button.' },
  listening_for_name: { name: 'Listening for my name', blurb: 'Only waiting to hear my name. Nothing leaves your computer.' },
  connecting: { name: 'Getting ready', blurb: 'Starting a session.' },
  live: { name: 'Listening', blurb: 'I can hear you and see your screen.' },
  speaking: { name: 'Speaking', blurb: 'Ripples while I talk.' },
  thinking: { name: 'Thinking', blurb: 'Dimmed and slow while I work it out.' },
  error: { name: 'Something went wrong', blurb: 'A clear message and a way to retry.' },
};

const S = {
  theme: 'light',
  themeSetting: 'light',
  glass: false,
  glassOpacity: 0.5,
  textScale: 1,
  chatMode: 'voice',
  hc: false,
  hcDark: false,
  big: true,
  dys: false,
  reduce: false,
  persona: 'marcus',
  phase: 'live',
  level: 2,
  locked: false,
  muted: false,
  tab: 'chat',
  settings: {
    helpLevelMode: 'auto',
    lockedLevel: 2,
    pacing: 'gentle',
    voiceSpeed: 1,
    captions: true,
    textOnly: false,
    explainJargon: true,
    teachBack: true,
    scamShield: true,
    doItForMeAllowed: false,
    carerSharing: false,
    pushToTalkOnly: false,
    listeningLight: true,
    demoMode: true,
    wakeEnabled: true,
    agency: 'off',
    showMenuBarIcon: true,
    launchAtLogin: false,
  },
};

const listeners = [];
function set(patch) {
  const changed = Object.keys(patch);
  Object.assign(S, patch);
  applyRoot();
  for (const fn of listeners) fn(changed);
}
const on = (fn) => listeners.push(fn);
const persona = () => PERSONAS[S.persona].displayName;

/* ---------- tiny DOM helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return el;
}
const NS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const ICONS = {
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
  check: '<path d="M4 12.5l5 5 11-11"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  doc: '<path d="M7 3h8l4 4v14H7z"/><path d="M15 3v4h4"/>',
  micoff: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3M4 4l16 16"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
};
function icon(name) {
  const w = h('span', { html: `<svg class="al-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>` });
  return w.firstChild;
}

/* ---------- root attributes ---------- */
// Keep in step with src/renderer/design/apply-settings.ts: glass never makes text-bearing areas less than 70% opaque.
function glassAlphas(opacity) {
  const o = Math.min(1, Math.max(0.35, opacity));
  return { shell: 0.7 + 0.3 * ((o - 0.35) / 0.65), card: Math.max(0.94, o) };
}
const sysDarkNow = () => matchMedia('(prefers-color-scheme: dark)').matches;
function applyRoot() {
  const r = document.documentElement;
  const wantsDark = S.themeSetting === 'auto' ? sysDarkNow() : S.themeSetting === 'dark';
  S.theme = wantsDark ? 'dark' : 'light';
  const dark = S.hc ? S.hcDark : wantsDark;
  r.setAttribute('data-theme', dark ? 'dark' : 'light');
  r.setAttribute('data-high-contrast', String(S.hc));
  r.setAttribute('data-big-annotations', String(S.big));
  r.setAttribute('data-dyslexia-font', String(S.dys));
  r.setAttribute('data-persona', S.persona);
  r.setAttribute('data-glass', String(S.glass && !S.hc));
  const g = glassAlphas(S.glassOpacity);
  r.style.setProperty('--glass-shell', (g.shell * 100).toFixed(1) + '%');
  r.style.setProperty('--glass-card', (g.card * 100).toFixed(1) + '%');
  r.style.setProperty('--ui-scale', String(S.textScale));
  if (S.reduce) r.setAttribute('data-motion', 'reduced');
  else r.removeAttribute('data-motion');
}

/* ---------- components ---------- */
function Orb(phase, size) {
  const el = h('div', { class: 'al-orb', 'data-phase': phase, role: 'img', 'aria-label': `${persona()}: ${PHASES[phase].name}` },
    h('span', { class: 'al-orb__halo' }), h('span', { class: 'al-orb__ring' }), h('span', { class: 'al-orb__core' }, phase === 'error' ? '!' : ''));
  if (size) el.style.setProperty('--orb-size', size + 'px');
  return el;
}

function lightState() {
  if (S.muted) return 'muted';
  if (S.phase === 'asleep' || S.phase === 'error') return 'off';
  if (S.phase === 'listening_for_name') return 'wake';
  return 'screen';
}
function lightText(state) {
  return {
    off: 'Not listening',
    wake: `Listening for “Hey ${persona()}”`,
    screen: 'I can see your screen',
    muted: 'Muted. I can’t hear you',
  }[state];
}
function ListeningLight(opts = {}) {
  const dot = h('span', { class: 'al-light__dot' });
  const text = h('span', { class: 'al-light__text' });
  const root = h('div', { class: 'al-light', role: 'status' }, dot, text);
  const update = () => {
    const st = lightState();
    root.dataset.state = st;
    text.textContent = lightText(st);
    root.setAttribute('aria-label', lightText(st));
  };
  update();
  on(update);
  return root;
}
function MuteButton() {
  const b = h('button', { class: 'al-btn al-btn--quiet al-mute', type: 'button', 'aria-pressed': 'false', onclick: () => set({ muted: !S.muted }) });
  const u = () => {
    b.replaceChildren(icon(S.muted ? 'micoff' : 'mic'));
    b.setAttribute('aria-pressed', String(S.muted));
    b.setAttribute('aria-label', S.muted ? 'Unmute the microphone' : 'Mute the microphone');
    b.title = S.muted ? 'Unmute' : 'Mute';
  };
  u();
  on(u);
  return b;
}

function LevelChip(opts = {}) {
  const variant = opts.variant || 'default';
  const bars = h('div', { class: 'al-level__bars', 'aria-hidden': 'true' }, [1, 2, 3, 4].map(() => h('span', { class: 'al-level__bar' })));
  const kicker = h('span', { class: 'al-level__kicker' });
  const name = h('span', { class: 'al-level__name' });
  const lock = h('span', { class: 'al-level__lock', hidden: true }, icon('lock'), h('span', { class: 'al-level__locktext' }, 'Locked'));
  const delta = h('span', { class: 'al-level__delta', 'aria-hidden': 'true' });
  const live = h('span', { class: 'al-sr', 'aria-live': 'polite' });
  const root = h('div', { class: 'al-level' + (variant === 'compact' ? ' al-level--compact' : '') + (variant === 'hero' ? ' al-level--hero' : ''), role: 'group' },
    bars, h('span', { class: 'al-level__text' }, kicker, name), lock, delta, live);
  let shown = null;
  let timer = 0;
  function render(level, locked, animate) {
    bars.querySelectorAll('.al-level__bar').forEach((b, i) => b.setAttribute('data-on', String(i < LEVEL_SUPPORT[level])));
    kicker.textContent = `Help level ${level} of 4`;
    lock.hidden = !locked;
    root.setAttribute('aria-label', `Help level ${level} of 4: ${LEVEL_NAMES[level]}${locked ? ', locked' : ''}`);
    const word = h('span', { class: 'al-level__word' }, LEVEL_NAMES[level]);
    const old = name.querySelector('.al-level__word:not(.is-leaving)');
    if (old && animate && shown !== level) {
      old.classList.add('is-leaving');
      word.classList.add('is-entering');
      setTimeout(() => old.remove(), 340);
    } else if (old) {
      old.remove();
    }
    name.append(word);
    if (animate && shown !== null && shown !== level) {
      const less = level > shown;
      delta.textContent = less ? 'Less help. You’re leading.' : 'More help, as you asked.';
      live.textContent = `Help level changed to ${LEVEL_NAMES[level]}. ${less ? 'Less help.' : 'More help.'}`;
      root.dataset.changing = 'false';
      void root.offsetWidth;
      root.dataset.changing = 'true';
      clearTimeout(timer);
      timer = setTimeout(() => (root.dataset.changing = 'false'), 3600);
    }
    shown = level;
  }
  render(opts.level ?? S.level, opts.locked ?? S.locked, false);
  if (!opts.fixed) on((c) => (c.includes('level') || c.includes('locked')) && render(S.level, S.locked, true));
  root.render = render;
  return root;
}

function StopButton(compact) {
  return h('button', { class: 'al-btn al-btn--danger al-stop' + (compact ? ' al-stop--compact' : ''), type: 'button', 'aria-label': 'Stop. I will stop listening and looking.', onclick: () => set({ phase: 'asleep', muted: false }) }, icon('stop'), 'Stop');
}

function Caption(speaker, text, final = true) {
  const who = speaker === 'user' ? 'You' : speaker === 'assistant' ? persona() : 'Note';
  return h('div', { class: 'al-caption', 'data-speaker': speaker, 'data-final': String(final) },
    h('span', { class: 'al-caption__who' }, who), h('p', { class: 'al-caption__text' }, text));
}

const KIND_ICON = { scam_check: 'shield', lookup: 'search', lesson_summary: 'doc' };
function AgentChipEl(chip, onCancel) {
  const open = { v: !!chip.open };
  const statusText = { running: 'Looking', done: 'Done', error: 'Couldn’t finish', cancelled: 'Stopped' }[chip.status];
  const status = h('span', { class: 'al-agent__status' },
    chip.status === 'running' ? h('span', { class: 'al-spinner', 'aria-hidden': 'true' }) : chip.status === 'done' ? icon('check') : chip.status === 'error' ? icon('alert') : icon('x'), statusText);
  const body = h('div', { class: 'al-agent__body', hidden: !open.v, id: 'agent-' + chip.id });
  if (chip.summary) body.append(h('p', {}, chip.summary));
  if (chip.flags) body.append(h('ul', { class: 'al-flags' }, chip.flags.map((f) => h('li', { class: 'al-flag' }, h('q', {}, f.phrase), ' – ', f.why))));
  if (chip.human) body.append(h('p', { class: 'al-small' }, chip.human));
  if (chip.status === 'running') body.append(h('button', { class: 'al-btn', type: 'button', onclick: () => onCancel(chip.id) }, 'Stop this check'));
  const head = h('button', { class: 'al-agent__head', type: 'button', 'aria-expanded': String(open.v), 'aria-controls': 'agent-' + chip.id, onclick: (e) => {
    open.v = !open.v;
    e.currentTarget.setAttribute('aria-expanded', String(open.v));
    body.hidden = !open.v;
  } }, icon(KIND_ICON[chip.kind]), h('span', { class: 'al-agent__title' }, chip.title), status, h('span', { class: 'al-agent__chev' }, icon('down')));
  return h('div', { class: 'al-agent', 'data-status': chip.status, role: 'listitem' }, head, body);
}

const agents = [
  { id: 'a1', kind: 'scam_check', title: 'Checking the text from “Royal Post”', status: 'done', open: true, summary: 'This looks like a scam. I found 3 warning signs.',
    flags: [
      { phrase: 'within 24 hours', why: 'Real services don’t rush you.' },
      { phrase: 'pay a £1.50 fee', why: 'Small fees are a common way in.' },
      { phrase: 'royalpost-redeliver.example', why: 'Not the real website address.' },
    ],
    human: 'Don’t tap the link. Use the official app, or call the number on your card.' },
  { id: 'a2', kind: 'lookup', title: 'Looking up how to turn on subtitles', status: 'running' },
  { id: 'a3', kind: 'lesson_summary', title: 'Writing your lesson summary', status: 'error', summary: 'I couldn’t reach the internet. Your progress is saved.' },
];
const agentTrays = [];
function AgentTray() {
  const tray = h('div', { class: 'al-tray', role: 'list', 'aria-label': 'Helpers working for you' });
  const draw = () => {
    tray.replaceChildren(...agents.map((a) => AgentChipEl(a, cancelAgent)));
  };
  tray.draw = draw;
  agentTrays.push(tray);
  draw();
  return tray;
}
function cancelAgent(id) {
  const a = agents.find((x) => x.id === id);
  if (a) a.status = 'cancelled';
  agentTrays.forEach((t) => t.draw());
}
function startAgent() {
  const id = 'n' + Date.now();
  agents.unshift({ id, kind: 'scam_check', title: 'Checking the message on screen', status: 'running' });
  agentTrays.forEach((t) => t.draw());
  setTimeout(() => {
    const a = agents.find((x) => x.id === id);
    if (a && a.status === 'running') {
      a.status = 'done';
      a.summary = 'No clear red flags, but still check directly with the sender.';
    }
    agentTrays.forEach((t) => t.draw());
  }, 2600);
}

function Stepper(n, total, label) {
  return h('div', { class: 'al-stepper' },
    h('div', { class: 'al-stepper__top' }, h('strong', {}, label), h('span', { class: 'al-stepper__count' }, `Step ${n} of ${total}`)),
    h('div', { class: 'al-stepper__dots', role: 'img', 'aria-label': `Step ${n} of ${total}` }, Array.from({ length: total }, (_, i) => h('span', { class: 'al-stepper__dot', 'data-state': i + 1 < n ? 'done' : i + 1 === n ? 'now' : 'todo' }))));
}

let switchId = 0;
function Switch(key, label, hint) {
  const id = 'sw' + ++switchId;
  const input = h('input', { type: 'checkbox', role: 'switch', id, onchange: () => set({ settings: { ...S.settings, [key]: input.checked } }) });
  input.checked = !!S.settings[key];
  on(() => (input.checked = !!S.settings[key]));
  return h('label', { class: 'al-switch', for: id },
    h('span', { class: 'al-switch__text' }, h('span', { class: 'al-switch__label' }, label), h('span', { class: 'al-switch__hint' }, hint)),
    input, h('span', { class: 'al-switch__track', 'aria-hidden': 'true' }, h('span', { class: 'al-switch__thumb' })));
}
function Seg(label, options, get, setter) {
  const btns = options.map(([value, text]) => h('button', { class: 'al-seg__btn', type: 'button', role: 'radio', onclick: () => setter(value) }, text));
  const root = h('div', { class: 'al-seg', role: 'radiogroup', 'aria-label': label }, btns);
  const u = () => btns.forEach((b, i) => b.setAttribute('aria-checked', String(get() === options[i][0])));
  u();
  on(u);
  return root;
}
function Field(label, hint, control) {
  return h('div', { class: 'al-field' }, h('span', { class: 'al-field__label' }, label), hint ? h('span', { class: 'al-small' }, hint) : null, control);
}
function Group(title, ...kids) {
  return h('section', { class: 'al-group', 'aria-label': title }, h('h3', { class: 'al-eyebrow' }, title), ...kids);
}
function setSetting(patch) {
  set({ settings: { ...S.settings, ...patch } });
}

/* ---------- annotation drawing (preview renderer for annotation-style.ts) ---------- */
const VB = { w: 640, h: 400 };
const nx = (v) => (v / 1000) * VB.w;
const ny = (v) => (v / 1000) * VB.h;
const px = (b) => ({ x: nx(b.xmin), y: ny(b.ymin), w: nx(b.xmax - b.xmin), h: ny(b.ymax - b.ymin) });
const styleNow = () => annotationStyle({ bigAnnotations: S.big, highContrast: S.hc, dyslexiaFont: S.dys }, { reducedMotion: S.reduce || matchMedia('(prefers-reduced-motion: reduce)').matches });

function layered(st, tone, factory, widthScale = 1) {
  const t = st.tones[tone];
  const g = sv('g');
  strokeLayers(st, tone, widthScale).forEach((layer, i, all) => {
    const el = factory({ fill: 'none', stroke: layer.color, 'stroke-width': layer.width, 'stroke-opacity': layer.opacity, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-dasharray': i === all.length - 1 && t.dash ? t.dash : null });
    g.append(el);
  });
  return g;
}
function anim(st, g, extra) {
  g.setAttribute('class', 'pv-in');
  g.style.setProperty('--pv-in-ms', st.transition.enterMs + 'ms');
  g.style.setProperty('--pv-in-scale', st.transition.enterFromScale);
  return g;
}
function echo(st, tone, shape) {
  if (!st.pulse.enabled) return null;
  const t = st.tones[tone];
  const el = shape({ fill: 'none', stroke: t.core, 'stroke-width': Math.max(2, st.stroke.core * 0.8), 'stroke-opacity': 1, class: 'pv-echo' });
  el.style.setProperty('--pv-echo-ms', st.pulse.periodMs + 'ms');
  el.style.setProperty('--pv-echo-n', t.pulseIterations === 'infinite' ? 'infinite' : String(t.pulseIterations));
  el.style.setProperty('--pv-echo-o', st.pulse.opacityFrom);
  el.style.setProperty('--pv-echo-s', st.pulse.scaleTo);
  return el;
}
function glowFilter(st) {
  return sv('filter', { id: 'pv-glow', x: '-30%', y: '-30%', width: '160%', height: '160%' }, sv('feGaussianBlur', { stdDeviation: st.glow.blur / 2 }));
}
function pillText(st, text, x, y, opts = {}) {
  const b = st.bubble;
  const size = (opts.size || b.fontSize) ;
  const lines = wrap(text, Math.max(10, Math.floor(b.maxWidth / (size * 0.52))));
  const wpx = Math.min(b.maxWidth, Math.max(...lines.map((l) => l.length)) * size * 0.52) + b.padding.x * 2;
  const hpx = lines.length * size * b.lineHeight + b.padding.y * 2;
  const g = sv('g');
  const bx = Math.max(4, Math.min(VB.w - wpx - 4, x));
  const by = Math.max(4, Math.min(VB.h - hpx - 4, y));
  g.append(sv('rect', { x: bx, y: by, width: wpx, height: hpx, rx: b.radius, fill: b.background, stroke: b.borderColor, 'stroke-width': b.borderWidth }));
  lines.forEach((l, i) => {
    const tx = sv('text', { x: bx + b.padding.x, y: by + b.padding.y + size * b.lineHeight * (i + 0.78), fill: b.color, 'font-family': b.fontFamily, 'font-size': size, 'font-weight': 700 }, l);
    g.append(tx);
  });
  return { g, box: { x: bx, y: by, w: wpx, h: hpx } };
}
function wrap(text, max) {
  const out = [];
  let line = '';
  for (const w of text.split(' ')) {
    if ((line + ' ' + w).trim().length > max && line) {
      out.push(line);
      line = w;
    } else line = (line + ' ' + w).trim();
  }
  if (line) out.push(line);
  return out;
}
function glyphEl(st, tone, cx, cy, r) {
  const t = st.tones[tone];
  const attrs = { fill: 'none', stroke: t.onCore, 'stroke-width': r * 0.2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
  if (t.glyph === 'check') return sv('path', { ...attrs, d: `M${cx - r * 0.45} ${cy + r * 0.02} L${cx - r * 0.1} ${cy + r * 0.38} L${cx + r * 0.5} ${cy - r * 0.35}`, class: 'pv-draw' });
  if (t.glyph === 'alert') return sv('g', {}, sv('path', { ...attrs, d: `M${cx} ${cy - r * 0.45} L${cx} ${cy + r * 0.1}` }), sv('circle', { cx, cy: cy + r * 0.42, r: r * 0.1, fill: t.onCore }));
  if (t.glyph === 'stop') return sv('path', { ...attrs, d: `M${cx - r * 0.38} ${cy - r * 0.38} L${cx + r * 0.38} ${cy + r * 0.38} M${cx + r * 0.38} ${cy - r * 0.38} L${cx - r * 0.38} ${cy + r * 0.38}` });
  return sv('path', { ...attrs, d: `M${cx - r * 0.35} ${cy - r * 0.35} L${cx + r * 0.4} ${cy} L${cx - r * 0.35} ${cy + r * 0.35} Z`, fill: t.onCore });
}
function badge(st, tone, cx, cy, n) {
  const t = st.tones[tone];
  const r = st.badge.diameter / 2;
  const g = sv('g');
  strokeLayers(st, tone, 0.7).forEach((l, i, all) => {
    g.append(sv('circle', { cx, cy, r: r + (all.length - 1 - i) * 0 + (i === 0 ? l.width / 2 - st.stroke.casing * 0.35 : 0), fill: i === all.length - 1 ? t.core : l.color, stroke: i === all.length - 1 ? 'none' : l.color, 'stroke-width': 0 }));
  });
  g.append(sv('text', { x: cx, y: cy + st.badge.fontSize * 0.36, 'text-anchor': 'middle', fill: t.onCore, 'font-family': st.badge.fontFamily, 'font-size': st.badge.fontSize, 'font-weight': 700 }, String(n)));
  return g;
}
function pointerShape(st, tone, x, y, size, withTag) {
  const t = st.tones[tone];
  const k = size / 26;
  const d = `M0 0 L0 22 L6 17 L10 26 L14 24 L10 15 L18 15 Z`;
  const g = sv('g', { transform: `translate(${x} ${y}) scale(${k})` });
  strokeLayers(st, tone, 0.55).forEach((l, i, all) => {
    g.append(sv('path', { d, fill: i === all.length - 1 ? t.core : l.color, stroke: l.color, 'stroke-width': l.width / k, 'stroke-linejoin': 'round', 'fill-opacity': i === all.length - 1 ? 0.92 : 1 }));
  });
  return g;
}

function render(svg, anns) {
  const st = styleNow();
  svg.replaceChildren();
  svg.setAttribute('viewBox', `0 0 ${VB.w} ${VB.h}`);
  svg.append(sv('defs', {}, glowFilter(st)));
  for (const a of anns) {
    const g = sv('g');
    const tone = a.tone;
    const t = st.tones[tone];
    if (a.kind === 'ring') {
      const b = px(a.box);
      const pad = st.ring.pad;
      const w = Math.max(st.ring.minSize, b.w + pad * 2);
      const hh = Math.max(st.ring.minSize, b.h + pad * 2);
      const x = b.x + b.w / 2 - w / 2;
      const y = b.y + b.h / 2 - hh / 2;
      const rx = Math.min(st.ring.radius, hh / 2);
      g.append(sv('rect', { x, y, width: w, height: hh, rx, fill: 'none', stroke: t.glow, 'stroke-width': st.stroke.core * 1.6, filter: 'url(#pv-glow)' }));
      g.append(layered(st, tone, (at) => sv('rect', { x, y, width: w, height: hh, rx, ...at })));
      const e = echo(st, tone, (at) => sv('rect', { x, y, width: w, height: hh, rx, ...at }));
      if (e) g.append(e);
      if (a.step != null) g.append(badge(st, tone, x - st.badge.offset * 0.2, y - st.badge.offset * 0.2, a.step));
      if (a.label) g.append(pillText(st, a.label, x, y + hh + st.stroke.halo + 4, { size: st.bubble.fontSize * 0.82 }).g);
    } else if (a.kind === 'badge') {
      g.append(badge(st, tone, nx(a.at.x), ny(a.at.y), a.n));
    } else if (a.kind === 'arrow') {
      const box = a.to.xmin != null ? px(a.to) : { x: nx(a.to.x), y: ny(a.to.y), w: 0, h: 0 };
      const c = { x: box.x + box.w / 2, y: box.y + box.h / 2 };
      const from = a.from ? { x: nx(a.from.x), y: ny(a.from.y) } : { x: c.x - 200, y: c.y + 120 };
      let dx = c.x - from.x;
      let dy = c.y - from.y;
      const len0 = Math.hypot(dx, dy) || 1;
      dx /= len0;
      dy /= len0;
      const tx = Math.abs(dx) < 1e-6 ? Infinity : (box.w / 2 + st.ring.pad) / Math.abs(dx);
      const ty = Math.abs(dy) < 1e-6 ? Infinity : (box.h / 2 + st.ring.pad) / Math.abs(dy);
      const reach = Math.min(tx, ty) + st.arrow.gap + st.stroke.halo / 2;
      const tip = { x: c.x - dx * reach, y: c.y - dy * reach };
      const hl = st.arrow.headLength;
      const base = { x: tip.x - dx * hl, y: tip.y - dy * hl };
      const mid = { x: (from.x + base.x) / 2, y: (from.y + base.y) / 2 };
      const L = Math.hypot(base.x - from.x, base.y - from.y);
      const ctrl = { x: mid.x - dy * L * st.arrow.curvature, y: mid.y + dx * L * st.arrow.curvature };
      const sh = `M${from.x} ${from.y} Q${ctrl.x} ${ctrl.y} ${base.x} ${base.y}`;
      const ex = base.x - ctrl.x;
      const ey = base.y - ctrl.y;
      const el = Math.hypot(ex, ey) || 1;
      const ux = ex / el;
      const uy = ey / el;
      const hw = st.arrow.headWidth / 2;
      const tipP = { x: base.x + ux * hl, y: base.y + uy * hl };
      const head = `${tipP.x},${tipP.y} ${base.x - uy * hw},${base.y + ux * hw} ${base.x + uy * hw},${base.y - ux * hw}`;
      g.append(sv('path', { d: sh, fill: 'none', stroke: t.glow, 'stroke-width': st.stroke.core * 2, filter: 'url(#pv-glow)' }));
      g.append(layered(st, tone, (at) => sv('path', { d: sh, ...at })));
      strokeLayers(st, tone, 0.5).forEach((l, i, all) => {
        g.append(sv('polygon', { points: head, fill: l.color, stroke: l.color, 'stroke-width': l.width * 0.8, 'stroke-linejoin': 'round', 'fill-opacity': 1 }));
      });
    } else if (a.kind === 'spotlight') {
      const b = px(a.box);
      const p = st.spotlight.pad;
      const x = b.x - p;
      const y = b.y - p;
      const w = b.w + p * 2;
      const hh = b.h + p * 2;
      g.append(sv('defs', {}, sv('mask', { id: 'pv-spot' }, sv('rect', { width: VB.w, height: VB.h, fill: '#fff' }),
        sv('rect', { x, y, width: w, height: hh, rx: st.spotlight.radius, fill: '#000', filter: st.spotlight.feather ? 'url(#pv-feather)' : null })),
        sv('filter', { id: 'pv-feather', x: '-20%', y: '-40%', width: '140%', height: '180%' }, sv('feGaussianBlur', { stdDeviation: st.spotlight.feather / 3 }))));
      g.append(sv('rect', { width: VB.w, height: VB.h, fill: st.spotlight.dimColor, 'fill-opacity': st.spotlight.dimOpacity, mask: 'url(#pv-spot)' }));
      g.append(layered(st, tone, (at) => sv('rect', { x, y, width: w, height: hh, rx: st.spotlight.radius, ...at }), 0.6));
    } else if (a.kind === 'tick') {
      const b = px(a.box);
      const tk = st.tick;
      const tnTone = a.ok ? tk.okTone : tk.notOkTone;
      const tt = st.tones[tnTone];
      const r = tk.size / 2;
      const cx = Math.min(VB.w - r - 6, b.x + b.w + tk.offset * 0.2);
      const cy = Math.max(r + 6, b.y - tk.offset * 0.2);
      g.append(sv('rect', { x: b.x - st.ring.pad, y: b.y - st.ring.pad, width: b.w + st.ring.pad * 2, height: b.h + st.ring.pad * 2, rx: Math.min(st.ring.radius, (b.h + st.ring.pad * 2) / 2), fill: 'none', stroke: tt.core, 'stroke-width': st.stroke.core * 0.7, 'stroke-dasharray': tt.dash }));
      strokeLayers(st, tnTone, 0.4).forEach((l, i, all) => {
        g.append(sv('circle', { cx, cy, r: r + (all.length - 1 - i === 0 ? 0 : all.length - 1 - i) * st.stroke.core * 0.5 * (i === 0 ? 1 : 0.5), fill: i === all.length - 1 ? tt.core : l.color }));
      });
      g.append(glyphEl(st, tnTone, cx, cy, r));
    } else if (a.kind === 'highlightText') {
      a.boxes.forEach((bx) => {
        const b = px(bx);
        const p = st.highlightText.pad;
        g.append(sv('rect', { x: b.x - p, y: b.y - p, width: b.w + p * 2, height: b.h + p * 2, rx: st.highlightText.radius, fill: t.wash }));
        g.append(layered(st, tone, (at) => sv('path', { d: `M${b.x - p} ${b.y + b.h + p} H${b.x + b.w + p}`, ...at }), 0.5));
      });
      if (a.note) {
        const last = px(a.boxes[a.boxes.length - 1]);
        g.append(pillText(st, a.note, last.x, last.y + last.h + st.highlightText.pad * 2 + 10, { size: st.bubble.fontSize * 0.82 }).g);
      }
    } else if (a.kind === 'bubble') {
      g.append(pillText(st, a.text, nx(a.at.x), ny(a.at.y)).g);
    } else if (a.kind === 'ghostCursor') {
      g.append(ghost(st, tone, a, svg));
    }
    svg.append(anim(st, g));
  }
}

let ghostRaf = 0;
function ghost(st, tone, a, svg) {
  const pts = a.path.map((p) => ({ x: nx(p.x), y: ny(p.y) }));
  const g = sv('g');
  const trail = Array.from({ length: st.ghostCursor.trail.count }, (_, i) => sv('circle', { r: 5 - i * 0.6, fill: st.tones[tone].core, stroke: st.tones[tone].casing, 'stroke-width': 1, opacity: 0 }));
  trail.forEach((c) => g.append(c));
  const cur = pointerShape(st, tone, pts[0].x, pts[0].y, st.ghostCursor.size);
  const tag = pillText(st, st.ghostCursor.tag, 0, 0, { size: st.ghostCursor.tagFontSize * 0.9 });
  const press = sv('circle', { r: st.ghostCursor.press.radius * 0.5, fill: 'none', stroke: st.tones[tone].core, 'stroke-width': st.stroke.core * 0.7, opacity: 0 });
  g.append(press, cur, tag.g);
  cancelAnimationFrame(ghostRaf);
  const total = pts.length - 1;
  const dist = pts.slice(1).reduce((s, p, i) => s + Math.hypot(p.x - pts[i].x, p.y - pts[i].y), 0);
  const dur = Math.min(st.ghostCursor.flight.maxMs, Math.max(st.ghostCursor.flight.minMs, (dist / st.ghostCursor.flight.pxPerSec) * 1000 * 2));
  const history = [];
  let start = performance.now();
  const place = (x, y) => {
    cur.setAttribute('transform', `translate(${x} ${y}) scale(${st.ghostCursor.size / 26})`);
    tag.g.setAttribute('transform', `translate(${Math.min(x + st.ghostCursor.size * 0.9, VB.w - tag.box.w - 8) - tag.box.x} ${Math.min(y + st.ghostCursor.size * 1.1, VB.h - tag.box.h - 8) - tag.box.y})`);
  };
  const at = (t) => {
    if (total === 0) return pts[0];
    const f = t * total;
    const i = Math.min(total - 1, Math.floor(f));
    const u = f - i;
    const p = pts[i];
    const q = pts[i + 1];
    const arc = Math.sin(Math.PI * u) * st.ghostCursor.flight.arcHeightFraction * Math.hypot(q.x - p.x, q.y - p.y);
    const nxv = -(q.y - p.y);
    const nyv = q.x - p.x;
    const nl = Math.hypot(nxv, nyv) || 1;
    return { x: p.x + (q.x - p.x) * u + (nxv / nl) * arc, y: p.y + (q.y - p.y) * u + (nyv / nl) * arc };
  };
  place(pts[0].x, pts[0].y);
  const tick = (now) => {
    if (!svg.isConnected || !g.isConnected) return;
    const e = now - start;
    const raw = Math.min(1, e / dur);
    const t = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
    const p = at(t);
    place(p.x, p.y);
    history.unshift(p);
    trail.forEach((c, i) => {
      const hp = history[(i + 1) * 3];
      if (hp && raw < 1) {
        c.setAttribute('cx', hp.x + 3);
        c.setAttribute('cy', hp.y + 3);
        c.setAttribute('opacity', String(st.ghostCursor.trail.opacity * (1 - i / trail.length)));
      } else c.setAttribute('opacity', '0');
    });
    if (history.length > 40) history.length = 40;
    if (raw >= 1) {
      if (a.pressAtEnd && !st.reducedMotion) {
        const pe = e - dur;
        const pr = Math.min(1, pe / st.ghostCursor.press.durationMs);
        press.setAttribute('cx', p.x);
        press.setAttribute('cy', p.y);
        press.setAttribute('r', String(st.ghostCursor.press.radius * (0.4 + pr * 0.8)));
        press.setAttribute('opacity', String(0.8 * (1 - pr)));
      }
      if (e > dur + st.ghostCursor.flight.dwellMs + 900) {
        start = now;
        history.length = 0;
        press.setAttribute('opacity', '0');
      }
    }
    ghostRaf = requestAnimationFrame(tick);
  };
  ghostRaf = requestAnimationFrame(tick);
  return g;
}

/* ---------- mock desktop ---------- */
function Mock(app) {
  const video = `<svg viewBox="0 0 24 24"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/></svg>`;
  if (app === 'messages') {
    return h('div', { class: 'mk-win', 'data-app': 'messages', html: `
      <div class="mk-main">
        <div class="mk-head"><div>Royal Post<small>+44 7700 900123 · not in your contacts</small></div></div>
        <div class="mk-chat">
          <div class="mk-msg" style="max-width:92%">Royal Post: your parcel is on hold.<br>Please <span data-flag>pay a £1.50 fee</span> <span data-flag>within 24 hours</span><br>or it will be sent back.<br><span data-flag>royalpost-redeliver.example</span></div>
          <div class="mk-msg" data-me="true">Who is this?</div>
        </div>
      </div>` });
  }
  return h('div', { class: 'mk-win', 'data-app': 'video', html: `
    <div class="mk-side"><h4>Chats</h4>
      <div class="mk-row" data-sel="true"><span class="mk-av"></span>Lily</div>
      <div class="mk-row"><span class="mk-av"></span>Sam</div>
      <div class="mk-row"><span class="mk-av"></span>Priya</div>
      <div class="mk-row"><span class="mk-av"></span>Dr Patel</div></div>
    <div class="mk-main">
      <div class="mk-head"><div>Lily<small>Online</small></div><span class="mk-go" data-ground-id="video-btn">${video}Video call</span></div>
      <div class="mk-chat">
        <div class="mk-msg">Are you free for a chat later?</div>
        <div class="mk-msg" data-me="true">Yes. Call me at four.</div>
        <div class="mk-msg">Lovely. I will show you the garden.</div>
      </div>
    </div>` });
}
function normBoxOf(el, screen) {
  const s = screen.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  return { xmin: ((r.left - s.left) / s.width) * 1000, ymin: ((r.top - s.top) / s.height) * 1000, xmax: ((r.right - s.left) / s.width) * 1000, ymax: ((r.bottom - s.top) / s.height) * 1000 };
}

const KINDS = [
  ['ring', 'Ring and number'],
  ['arrow', 'Arrow'],
  ['spotlight', 'Spotlight'],
  ['ghost', 'Ghost cursor'],
  ['note', 'Note'],
  ['tick', 'Done tick'],
  ['miss', 'Gentle miss'],
  ['flags', 'Scam red flags'],
];
const annState = { kind: 'ring', screenTheme: 'light' };
function AnnotationDemo() {
  const screen = h('div', { class: 'pv-screen', 'data-screen-theme': 'light' });
  const svg = sv('svg', { class: 'pv-ann', role: 'img', 'aria-label': 'Preview of an on-screen annotation' });
  const caption = h('p', { class: 'pv-hint', 'aria-live': 'polite' });
  const kindBtns = KINDS.map(([k, label]) => h('button', { class: 'pv-chipbtn', type: 'button', 'aria-pressed': 'false', onclick: () => { annState.kind = k; draw(); } }, label));
  const themeBtns = ['light', 'dark'].map((t) => h('button', { class: 'pv-chipbtn', type: 'button', 'aria-pressed': 'false', onclick: () => { annState.screenTheme = t; draw(); } }, t === 'light' ? 'Light screen' : 'Dark screen'));
  const notes = {
    ring: 'A ring and a numbered badge, one step at a time. The line has a white edge and a dark edge, so it shows on any screen.',
    arrow: 'The arrow stops short of the button, so it never covers what you need to press.',
    spotlight: 'Everything else dims. Use it when a screen is busy.',
    ghost: 'Show me: the cursor moves and presses as a picture only. It never clicks.',
    note: 'A short note beside the target, in large type.',
    tick: 'A tick appears when I can see you did it.',
    miss: 'If a step did not work, a gentle amber mark. Never red, never a failure.',
    flags: 'Scam Shield underlines the words that worry me, each with a reason. I never say a message is “safe”.',
  };
  function draw() {
    const app = annState.kind === 'flags' ? 'messages' : 'video';
    screen.dataset.screenTheme = annState.screenTheme;
    screen.replaceChildren(Mock(app), svg);
    kindBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(KINDS[i][0] === annState.kind)));
    themeBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(['light', 'dark'][i] === annState.screenTheme)));
    caption.textContent = notes[annState.kind];
    requestAnimationFrame(() => {
      let anns = [];
      if (app === 'messages') {
        const boxes = [...screen.querySelectorAll('[data-flag]')].map((e) => normBoxOf(e, screen));
        anns = [{ id: 'f', kind: 'highlightText', tone: 'danger', boxes, note: 'Rushing you is a warning sign.' }];
      } else {
        const btn = normBoxOf(screen.querySelector('[data-ground-id]'), screen);
        const cx = (btn.xmin + btn.xmax) / 2;
        const cy = (btn.ymin + btn.ymax) / 2;
        const k = annState.kind;
        if (k === 'ring') anns = [{ id: 'r', kind: 'ring', tone: 'guide', box: btn, step: 1, label: 'Tap Video call' }];
        if (k === 'arrow') anns = [{ id: 'a', kind: 'arrow', tone: 'guide', to: btn, from: { x: cx - 330, y: cy + 330 } }, { id: 'ar', kind: 'ring', tone: 'guide', box: btn }];
        if (k === 'spotlight') anns = [{ id: 's', kind: 'spotlight', tone: 'guide', box: btn }];
        if (k === 'ghost') anns = [{ id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 220, y: 700 }, { x: 520, y: 420 }, { x: cx, y: cy }], pressAtEnd: true }, { id: 'gr', kind: 'ring', tone: 'guide', box: btn }];
        if (k === 'note') anns = [{ id: 'n', kind: 'bubble', tone: 'guide', at: { x: btn.xmin - 80, y: btn.ymax + 60 }, text: 'This starts the call with Lily.' }, { id: 'nr', kind: 'ring', tone: 'guide', box: btn }];
        if (k === 'tick') anns = [{ id: 't', kind: 'tick', tone: 'success', box: btn, ok: true }];
        if (k === 'miss') anns = [{ id: 'm', kind: 'tick', tone: 'warn', box: btn, ok: false }];
      }
      render(svg, anns);
    });
  }
  on((c) => (c.includes('big') || c.includes('hc') || c.includes('dys') || c.includes('reduce')) && draw());
  draw();
  const legend = h('div', { class: 'pv-tones' }, ['guide', 'success', 'warn', 'danger'].map((tone) => {
    const st = styleNow();
    const s2 = sv('svg', { viewBox: '0 0 72 30', 'aria-hidden': 'true' });
    s2.append(layered(st, tone, (at) => sv('path', { d: 'M8 15 H64', ...at }), 0.7));
    return h('div', { class: 'pv-tone' }, s2, st.tones[tone].name);
  }));
  on((c) => {
    if (!(c.includes('big') || c.includes('hc'))) return;
    legend.replaceChildren(...['guide', 'success', 'warn', 'danger'].map((tone) => {
      const st = styleNow();
      const s2 = sv('svg', { viewBox: '0 0 72 30', 'aria-hidden': 'true' });
      s2.append(layered(st, tone, (at) => sv('path', { d: 'M8 15 H64', ...at }), 0.7));
      return h('div', { class: 'pv-tone' }, s2, st.tones[tone].name);
    }));
  });
  return h('div', { class: 'pv-card' }, h('div', { class: 'pv-row' }, kindBtns), screen, caption, h('div', { class: 'pv-row' }, themeBtns), legend);
}

/* the small annotation preview inside Settings */
function AnnotationPreview() {
  const svg = sv('svg', { viewBox: '0 0 320 150', role: 'img', 'aria-label': 'What on-screen marks will look like with these settings' });
  const draw = () => {
    const st = styleNow();
    svg.replaceChildren(sv('defs', {}, glowFilter(st)));
    svg.append(sv('rect', { x: 30, y: 48, width: 110, height: 44, rx: 10, fill: '#e8ecf3' }), sv('text', { x: 85, y: 76, 'text-anchor': 'middle', 'font-size': 18, 'font-weight': 700, fill: '#1d2330', 'font-family': 'system-ui' }, 'Send'));
    const x = 22;
    const y = 40;
    const w = 126;
    const hh = 60;
    svg.append(layered(st, 'guide', (at) => sv('rect', { x, y, width: w, height: hh, rx: Math.min(st.ring.radius, hh / 2), ...at })));
    svg.append(badge(st, 'guide', x + 4, y + 2, 1));
    const from = { x: 270, y: 120 };
    const tip = { x: 172, y: 86 };
    svg.append(layered(st, 'guide', (at) => sv('path', { d: `M${from.x} ${from.y} Q${(from.x + tip.x) / 2 + 6} ${(from.y + tip.y) / 2 + 16} ${tip.x + 14} ${tip.y + 6}`, ...at })));
    svg.append(sv('polygon', { points: `${tip.x},${tip.y} ${tip.x + 20},${tip.y - 2} ${tip.x + 10},${tip.y + 16}`, fill: st.tones.guide.core, stroke: st.tones.guide.casing, 'stroke-width': st.stroke.core * 0.6, 'stroke-linejoin': 'round' }));
  };
  draw();
  on((c) => (c.includes('big') || c.includes('hc') || c.includes('reduce')) && draw());
  return h('div', { class: 'al-preview' }, svg);
}

/* ---------- settings: Basics always, everything else under More ---------- */
let uid = 0;
function SwitchOn(label, hint, get, setter, disabled) {
  const id = 'sx' + ++uid;
  const input = h('input', { type: 'checkbox', role: 'switch', id, onchange: () => setter(input.checked) });
  const u = () => { input.checked = !!get(); input.disabled = !!(disabled && disabled()); };
  u();
  on(u);
  return h('label', { class: 'al-switch', for: id }, h('span', { class: 'al-switch__text' }, h('span', { class: 'al-switch__label' }, label), hint ? h('span', { class: 'al-switch__hint' }, hint) : null), input, h('span', { class: 'al-switch__track', 'aria-hidden': 'true' }, h('span', { class: 'al-switch__thumb' })));
}
function SetRow(label, control, hint) {
  return h('div', { class: 'al-setrow' }, h('span', { class: 'al-setrow__label' }, label), control, hint ? h('span', { class: 'al-small' }, hint) : null);
}
function RangeRow(label, min, max, step, get, setter, left, right) {
  const input = h('input', { class: 'al-range', type: 'range', min: String(min), max: String(max), step: String(step), 'aria-label': label, oninput: (e) => setter(Number(e.target.value)) });
  input.value = String(get());
  on(() => (input.value = String(get())));
  return SetRow(label, h('div', { class: 'al-rangewrap' }, h('span', { 'aria-hidden': 'true' }, left), input, h('span', { 'aria-hidden': 'true' }, right)));
}
function SettingsPanel() {
  const root = h('div', { class: 'al-settings' });
  let moreOpen = false;
  const lockedRow = SetRow('Keep me at', Seg('Help level to keep', [[1, 'Watch me'], [2, 'Walk with me'], [3, 'Nudge me'], [4, 'On my own']], () => S.settings.lockedLevel, (v) => { setSetting({ lockedLevel: v }); set({ level: v }); }));
  const lockU = () => (lockedRow.hidden = S.settings.helpLevelMode !== 'locked');
  on(lockU);
  lockU();
  const seeRow = RangeRow('See-through', 0.35, 1, 0.05, () => S.glassOpacity, (v) => set({ glassOpacity: v }), 'More', 'Less');
  const seeU = () => (seeRow.hidden = !(S.glass && !S.hc));
  on(seeU);
  seeU();
  const basics = h('section', { class: 'al-group', 'aria-label': 'Basics' }, h('h3', { class: 'al-eyebrow' }, 'Basics'),
    SetRow('Companion', Seg('Companion', Object.entries(PERSONAS).map(([id, p]) => [id, p.displayName]), () => S.persona, (v) => set({ persona: v }))),
    RangeRow('Text size', 0.9, 1.5, 0.05, () => S.textScale, (v) => set({ textScale: v }), 'Smaller', 'Larger'),
    SwitchOn('Easier-to-read font', 'OpenDyslexic', () => S.dys, (v) => set({ dys: v })),
    SetRow('Theme', Seg('Theme', [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']], () => S.themeSetting, (v) => set({ themeSetting: v }))),
    SwitchOn('Glass look', '', () => S.glass && !S.hc, (v) => set({ glass: v }), () => S.hc),
    seeRow,
    SwitchOn('Captions', '', () => S.settings.captions, (v) => setSetting({ captions: v })),
    SwitchOn('High contrast', '', () => S.hc, (v) => set({ hc: v })));
  const moreBtn = h('button', { class: 'al-btn al-more', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'pv-more-settings', onclick: () => { moreOpen = !moreOpen; draw(); } });
  const sw = (label, hint, key) => SwitchOn(label, hint, () => S.settings[key], (v) => setSetting({ [key]: v }));
  const group = (title, ...kids) => h('section', { class: 'al-group', 'aria-label': title }, h('h3', { class: 'al-eyebrow' }, title), ...kids);
  const more = h('div', { id: 'pv-more-settings', class: 'al-settings' },
    group('Help',
      SetRow('Help level', Seg('Help level mode', [['auto', 'Adjust for me'], ['locked', 'Keep it fixed']], () => S.settings.helpLevelMode, (v) => { setSetting({ helpLevelMode: v }); set({ locked: v === 'locked' }); })),
      lockedRow,
      SetRow('Pace', Seg('Pace', [['gentle', 'Gentle'], ['fast', 'Quick']], () => S.settings.pacing, (v) => setSetting({ pacing: v }))),
      RangeRow('Voice speed', 0.75, 1.25, 0.05, () => S.settings.voiceSpeed, (v) => setSetting({ voiceSpeed: v }), 'Slower', 'Faster'),
      sw('Ask me to explain it back', '', 'teachBack'), sw('Explain computer words', '', 'explainJargon'), sw('Demo mode', 'Move up after one clean try', 'demoMode')),
    group('On screen', SwitchOn('Big marks', '', () => S.big, (v) => set({ big: v })), AnnotationPreview(), sw('Text only, no speaking', '', 'textOnly')),
    group('Listening', sw('Listen for my name', '', 'wakeEnabled'), sw('Only when I press a key', '', 'pushToTalkOnly'), sw('Show the listening light', '', 'listeningLight')),
    group('Safety', sw('Scam check', '', 'scamShield'),
      SetRow('Let me do things for you', Seg('Let me do things for you', [['off', 'Off'], ['ask_each', 'Ask each time'], ['ask_per_task', 'Ask per task']], () => S.settings.agency || 'off', (v) => setSetting({ agency: v })), 'Off means I only show you how.')),
    group('Menu bar', sw('Show in the menu bar', '', 'showMenuBarIcon'), sw('Open at login', '', 'launchAtLogin')),
    group('Other', h('div', { class: 'al-setrow' }, h('button', { class: 'al-btn', type: 'button' }, 'Run demo')), h('div', { class: 'al-setrow' }, h('button', { class: 'al-btn', type: 'button' }, 'Set up again'))));
  function draw() {
    moreBtn.setAttribute('aria-expanded', String(moreOpen));
    moreBtn.replaceChildren(moreOpen ? 'Fewer settings' : 'More settings', icon('down'));
    root.replaceChildren(basics, moreBtn, ...(moreOpen ? [more] : []));
  }
  draw();
  return root;
}

/* ---------- profile ("About you"): the learner's own file ---------- */
const PROFILE_SEED = `# My Alongside profile

> This file is yours. Read it, change it, or delete any line and Alongside will follow what it says here.

## About me & accessibility

- Call me Peggy
- I find small text hard to read

## Goals

- See my granddaughter Lily on a video call
- Send photos to my son

## Skills

| Skill | Level |
|---|---|
| Start a video call | 2 |

## What works for me

- Comparing the contacts list to a phone book helped
- Being asked what I would try before being told

## Jargon to avoid

- browser, URL, swipe

## Who can see what

- Nobody sees anything unless you switch on carer sharing in Settings.

## Last session

- yesterday · Start a video call · Found the green Start call button with one hint.
`;
const fakeFile = { content: PROFILE_SEED, revision: 1, stale: false };
function fakeWrite(content, revision) {
  const out = (ok, conflict) => ({ ok, conflict, content: fakeFile.content, revision: fakeFile.revision });
  if (fakeFile.stale) {
    fakeFile.stale = false;
    fakeFile.content += '\n- (someone changed this file)';
    fakeFile.revision += 1;
    return out(false, true);
  }
  if (revision !== fakeFile.revision) return out(false, true);
  fakeFile.content = content;
  fakeFile.revision += 1;
  return out(true, false);
}
const profileViews = [];
function ProfileTab() {
  const root = h('div', { class: 'al-profile' });
  const st = { doc: { content: fakeFile.content, revision: fakeFile.revision }, notice: '', adds: {}, adding: null, more: false, forgetting: null, editing: false, draft: '', latest: null };
  const write = (content) => {
    const r = fakeWrite(content, st.doc.revision);
    st.doc = { content: r.content, revision: r.revision };
    profileViews.forEach((v) => v !== api && v.sync());
    return r.ok ? 'ok' : r.conflict ? 'conflict' : 'rejected';
  };
  const STALE = 'This changed while you were looking, so I have loaded the latest. ';
  const forget = (indices) => {
    st.forgetting = null;
    const r = write(removeLines(st.doc.content, indices));
    st.notice = r === 'ok' ? 'Forgotten.' : STALE + 'Nothing was removed. Please try again.';
    draw();
  };
  function lines(section) {
    const frag = document.createDocumentFragment();
    if (section.lines.length === 0) frag.append(h('p', { class: 'al-small' }, 'Nothing written down yet.'));
    else frag.append(h('ul', { class: 'al-lines' }, section.lines.map((l) => h('li', { class: 'al-line' }, h('span', { class: 'al-line__text' }, l.text),
      h('button', { class: 'al-btn al-btn--quiet al-line__forget', type: 'button', 'aria-label': 'Forget: ' + l.text, onclick: () => forget([l.index]) }, 'Forget')))));
    if (section.lines.length > 1) {
      frag.append(st.forgetting === section.headingIndex
        ? h('div', { class: 'al-forgetrow', role: 'group', 'aria-label': 'Forget all of these?' }, h('span', {}, `Forget all ${section.lines.length}?`),
          h('button', { class: 'al-btn', type: 'button', onclick: () => forget(section.lines.map((l) => l.index)) }, 'Yes, forget them'),
          h('button', { class: 'al-btn al-btn--quiet', type: 'button', onclick: () => { st.forgetting = null; draw(); } }, 'Keep them'))
        : h('button', { class: 'al-btn al-btn--quiet al-forgetall', type: 'button', onclick: () => { st.forgetting = section.headingIndex; draw(); } }, 'Forget all of these'));
    }
    return frag;
  }
  function confirmDelete() {
    const host = root.closest('[data-modal-host]') || document.body;
    const close = () => modal.remove();
    const choose = (yes) => (e) => {
      if (!e.isTrusted) return;
      close();
      if (!yes) return;
      let r = write(blankProfile());
      if (r === 'conflict') r = write(blankProfile());
      st.notice = r === 'ok' ? 'Everything is deleted. I start again from nothing.' : 'I could not delete it. Please try again.';
      draw();
    };
    const dlg = h('div', { class: 'al-modal', role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'pq', tabindex: '-1' },
      h('p', { class: 'al-eyebrow' }, 'Please check'),
      h('h2', { class: 'al-modal__q', id: 'pq' }, 'Delete everything I know about you? This cannot be undone.'),
      h('div', { class: 'al-modal__choices' }, h('button', { class: 'al-btn al-btn--lg al-btn--danger', type: 'button', onclick: choose(true) }, 'Yes, delete everything'),
        h('button', { class: 'al-btn al-btn--lg', type: 'button', onclick: choose(false) }, 'No, keep it')),
      h('p', { class: 'al-modal__note' }, 'Only a click or tap here can answer. Nothing I say or read on screen can.'));
    const modal = h('div', { class: 'al-scrim' }, dlg);
    host.append(modal);
    dlg.focus();
  }
  function draw() {
    const sections = parseProfile(st.doc.content);
    const kids = [];
    if (st.notice) kids.push(h('p', { class: 'al-note', role: 'status' }, st.notice));
    EDITABLE_KEYS.forEach((key) => {
      const section = sections.find((s) => s.key === key);
      const copy = SECTION_COPY[key];
      let tail;
      if (st.adding === key) {
        const input = h('input', { class: 'al-input', type: 'text', maxlength: '160', 'aria-label': 'Add to ' + copy.title, oninput: (e) => { st.adds[key] = e.target.value; } });
        input.value = st.adds[key] || '';
        tail = h('form', { class: 'al-addrow', onsubmit: (e) => {
          e.preventDefault();
          const text = cleanNote(st.adds[key] || '');
          if (!text) return;
          const r = write(addLine(st.doc.content, key, text));
          if (r === 'ok') { st.adds[key] = ''; st.adding = null; st.notice = 'Written down.'; } else st.notice = STALE + 'Your words are still in the box. Press Add again.';
          draw();
        } }, input, h('button', { class: 'al-btn al-btn--primary', type: 'submit' }, 'Add'));
        setTimeout(() => input.focus(), 0);
      } else tail = h('button', { class: 'al-btn al-btn--quiet al-forgetall al-addbtn', type: 'button', onclick: () => { st.adding = key; draw(); } }, 'Add a line');
      kids.push(h('section', { class: 'al-group', 'aria-label': copy.title }, h('h3', { class: 'al-eyebrow' }, copy.title), section ? lines(section) : h('p', { class: 'al-small' }, 'Nothing yet.'), tail));
    });
    sections.filter((s) => s.key === 'other' && s.lines.length).forEach((s) => kids.push(h('section', { class: 'al-group' }, h('h3', { class: 'al-eyebrow' }, s.heading), lines(s))));
    const status = h('p', { role: 'status' });
    const setStatus = () => (status.textContent = S.settings.carerSharing ? 'Someone you trust sees a short summary. Never your screen.' : 'Nobody else. Sharing is off.');
    setStatus();
    on((c) => c.includes('settings') && status.isConnected && setStatus());
    kids.push(h('section', { class: 'al-group', 'aria-label': 'Who can see what' }, h('h3', { class: 'al-eyebrow' }, 'Who can see what'), status,
      SwitchOn('Share my progress', '', () => S.settings.carerSharing, (v) => setSetting({ carerSharing: v }))));
    const last = sections.find((s) => s.key === 'lastSession');
    if (last && last.lines[0]) kids.push(h('section', { class: 'al-group', 'aria-label': 'Last session' }, h('h3', { class: 'al-eyebrow' }, 'Last time'), h('p', {}, last.lines[0].text)));
    kids.push(h('button', { class: 'al-btn al-more', type: 'button', 'aria-expanded': String(st.more), onclick: () => { st.more = !st.more; draw(); } }, st.more ? 'Less' : 'More', icon('down')));
    if (st.more) {
      const editor = [];
      if (st.editing) {
        const ta = h('textarea', { class: 'al-textarea', id: 'al-profile-draft-' + profileViews.indexOf(api), 'aria-label': 'Your profile, as text', oninput: (e) => { st.draft = e.target.value; } });
        ta.value = st.draft;
        editor.push(ta);
        if (st.latest !== null) {
          editor.push(h('div', { class: 'al-conflict', role: 'alert' }, h('strong', {}, 'It changed while you were editing.'), h('span', {}, 'Your text is kept above. Here is the latest.'), h('pre', { class: 'al-latest' }, st.latest),
            h('div', { class: 'al-actions' }, h('button', { class: 'al-btn', type: 'button', onclick: () => { st.draft = st.latest; st.latest = null; draw(); } }, 'Use the latest'),
              h('button', { class: 'al-btn al-btn--primary', type: 'button', onclick: () => save() }, 'Save mine over it'))));
        } else {
          editor.push(h('div', { class: 'al-actions' }, h('button', { class: 'al-btn al-btn--primary', type: 'button', onclick: () => save() }, 'Save'),
            h('button', { class: 'al-btn', type: 'button', onclick: () => { st.editing = false; st.latest = null; draw(); } }, 'Discard changes')));
        }
      } else {
        editor.push(h('button', { class: 'al-btn', type: 'button', onclick: () => { st.draft = st.doc.content; st.latest = null; st.editing = true; draw(); } }, 'Edit the whole file'),
          h('button', { class: 'pv-chipbtn', type: 'button', onclick: () => { fakeFile.stale = true; st.notice = 'Demo: the next save will act as if someone else changed the file.'; draw(); } }, 'Demo: make the next save fail'));
      }
      kids.push(h('div', { class: 'al-profile' },
        h('section', { class: 'al-group', 'aria-label': 'Edit the whole file' }, h('h3', { class: 'al-eyebrow' }, 'The whole file'), ...editor),
        h('section', { class: 'al-group al-danger', 'aria-label': 'Delete everything' }, h('h3', { class: 'al-eyebrow' }, 'Start again'),
          h('button', { class: 'al-btn al-btn--danger', type: 'button', onclick: confirmDelete }, 'Delete everything I know about you'))));
    }
    const focused = root.contains(document.activeElement) ? document.activeElement.getAttribute('aria-label') : null;
    root.replaceChildren(...kids);
    if (focused) [...root.querySelectorAll('[aria-label]')].find((e) => e.getAttribute('aria-label') === focused && e.matches('input, textarea'))?.focus();
  }
  function save() {
    const r = write(st.draft);
    if (r === 'ok') { st.editing = false; st.latest = null; st.notice = 'Saved.'; } else st.latest = st.doc.content;
    draw();
  }
  const api = { el: root, sync: () => { if (!st.editing) { st.doc = { content: fakeFile.content, revision: fakeFile.revision }; draw(); } else if (st.doc.revision !== fakeFile.revision) { st.doc = { content: fakeFile.content, revision: fakeFile.revision }; } } };
  profileViews.push(api);
  draw();
  return root;
}

/* ---------- progress ---------- */
const EXAMPLE = {
  hints: [6, 5, 5, 3, 3, 2, 1, 0],
  confidence: [2, 2, 3, 3, 3, 4, 4, 5],
  can: [['Start a video call with family', '12 Oct'], ['Spot a suspicious text message', '19 Oct'], ['Make the text bigger', '26 Oct']],
  skills: [['Video call', 'On my own', 4], ['Spot a scam', 'Walk with me', 2], ['Bigger text', 'Nudge me', 3]],
};
function HintsChart() {
  const d = EXAMPLE.hints;
  const W = 340, H = 210, L = 34, R = 8, T = 22, B = 40;
  const max = 6;
  const pw = W - L - R, ph = H - T - B;
  const bw = pw / d.length;
  const y = (v) => T + ph - (v / max) * ph;
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Bar chart. Hints I gave you in each of your last ${d.length} tasks: ${d.join(', ')}. The number goes down.` });
  [0, 2, 4, 6].forEach((v) => {
    svg.append(sv('line', { class: 'al-chart__grid', x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    svg.append(sv('text', { x: L - 8, y: y(v) + 4, 'text-anchor': 'end' }, String(v)));
  });
  d.forEach((v, i) => {
    const x = L + i * bw + bw * 0.18;
    const w = bw * 0.64;
    if (v > 0) svg.append(sv('rect', { class: 'al-chart__bar', x, y: y(v), width: w, height: y(0) - y(v), rx: 4 }));
    else svg.append(sv('rect', { class: 'al-chart__bar', x, y: y(0) - 4, width: w, height: 4, rx: 2 }));
    svg.append(sv('text', { class: 'al-chart__val', x: x + w / 2, y: y(v) - 6, 'text-anchor': 'middle' }, String(v)));
    svg.append(sv('text', { x: x + w / 2, y: H - B + 18, 'text-anchor': 'middle' }, String(i + 1)));
  });
  svg.append(sv('text', { x: L + pw / 2, y: H - 6, 'text-anchor': 'middle' }, 'Task number, oldest to newest'));
  return h('div', { class: 'al-chart' }, h('h3', { class: 'al-h3' }, 'Hints I gave you'), svg, h('p', { class: 'al-chart__note' }, 'Fewer hints each time means you need me less. That is the goal.'), h('p', { class: 'al-small' }, 'Example data'));
}
function ConfidenceChart() {
  const d = EXAMPLE.confidence;
  const W = 340, H = 150, L = 34, R = 16, T = 14, B = 26;
  const pw = W - L - R, ph = H - T - B;
  const x = (i) => L + (i / (d.length - 1)) * pw;
  const y = (v) => T + ph - ((v - 1) / 4) * ph;
  const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Line chart. Your own confidence rating from 1 to 5 after each task: ${d.join(', ')}.` });
  [1, 3, 5].forEach((v) => {
    svg.append(sv('line', { class: 'al-chart__grid', x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    svg.append(sv('text', { x: L - 8, y: y(v) + 4, 'text-anchor': 'end' }, String(v)));
  });
  svg.append(sv('path', { class: 'al-chart__line', d: d.map((v, i) => `${i ? 'L' : 'M'}${x(i)} ${y(v)}`).join(' ') }));
  d.forEach((v, i) => svg.append(sv('circle', { class: 'al-chart__dot', cx: x(i), cy: y(v), r: i === d.length - 1 ? 7 : 4 })));
  svg.append(sv('text', { class: 'al-chart__val', x: x(d.length - 1), y: y(d[d.length - 1]) - 14, 'text-anchor': 'end' }, `${d[d.length - 1]} of 5`));
  svg.append(sv('text', { x: L + pw / 2, y: H - 4, 'text-anchor': 'middle' }, 'How sure you felt, 1 worried to 5 confident'));
  return h('div', { class: 'al-chart' }, h('h3', { class: 'al-h3' }, 'How you felt'), svg, h('p', { class: 'al-small' }, 'Example data'));
}
function ProgressView() {
  return h('div', { class: 'al-progress' },
    h('section', { class: 'al-section' }, h('h3', { class: 'al-h2' }, 'Things you can do now'),
      h('ul', { class: 'al-can' }, EXAMPLE.can.map(([t, d]) => h('li', { class: 'al-can__item' }, h('span', { class: 'al-can__tick' }, icon('check')), h('span', { class: 'al-can__text' }, t), h('span', { class: 'al-can__date' }, d))))),
    h('section', { class: 'al-section' }, h('h3', { class: 'al-h2' }, 'Your skills'),
      h('ul', { class: 'al-tree' }, EXAMPLE.skills.map(([n, state, lv]) => h('li', { class: 'al-skill' },
        h('div', { class: 'al-skill__top' }, h('span', { class: 'al-skill__name' }, n), h('span', { class: 'al-skill__state' }, state)),
        h('div', { class: 'al-skill__fill', role: 'img', 'aria-label': `${n}: ${state}` }, [1, 2, 3, 4].map((i) => h('span', { 'data-on': String(i >= 5 - lv) }))))))),
    HintsChart(), ConfidenceChart());
}

/* ---------- confirm ---------- */
function ConfirmDemo() {
  const result = h('p', { class: 'pv-result', 'aria-live': 'polite' }, 'Nothing has been answered yet.');
  const frame = h('div', { class: 'pv-frame' });
  const open = h('button', { class: 'al-btn al-btn--primary', type: 'button', onclick: show }, 'Show the question');
  frame.append(h('p', { class: 'al-muted' }, 'The question appears here.'));
  function show() {
    result.textContent = 'Waiting for a real click.';
    const q = 'May I click the green “Send” button for you?';
    const no = h('button', { class: 'al-btn al-btn--lg', type: 'button', onclick: () => answer('No, leave it') }, 'No, leave it');
    const yes = h('button', { class: 'al-btn al-btn--lg al-btn--primary', type: 'button', onclick: () => answer('Yes, go ahead') }, 'Yes, go ahead');
    const modal = h('div', { class: 'al-scrim' }, h('div', { class: 'al-modal', role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'cq', 'aria-describedby': 'cn' },
      h('p', { class: 'al-eyebrow' }, `${persona()} is asking`), h('h2', { class: 'al-modal__q', id: 'cq' }, q),
      h('div', { class: 'al-modal__choices' }, yes, no),
      h('p', { class: 'al-modal__note', id: 'cn' }, 'Only a click or tap here can answer. Nothing I say or read on screen can.')));
    frame.append(modal);
    no.focus();
    function answer(c) {
      modal.remove();
      result.textContent = `You chose: ${c}.`;
    }
  }
  return h('div', { class: 'pv-card' }, h('div', { class: 'pv-row' }, open), frame, result);
}

/* ---------- chat ---------- */
const chat = {
  messages: [
    { id: 'u1', role: 'user', text: 'How do I make the writing bigger?', final: true },
    { id: 'a1', role: 'assistant', text: 'Let’s do it together. Look for the gear icon in the top right.', final: true },
  ],
};
const chatListeners = [];
function pushChat(m) {
  const i = chat.messages.findIndex((x) => x.id === m.id);
  if (i < 0) chat.messages.push(m);
  else chat.messages[i] = m;
  chatListeners.forEach((f) => f());
}
let chatN = 0;
function replyFor(text) {
  if (/bigger|size|small|read/i.test(text)) return 'Open System Settings, then Displays. I will point to each one.';
  if (/photo|picture/i.test(text)) return 'We can send it from Messages. Open Messages and tap the photo button.';
  if (/scam|text from|bank/i.test(text)) return 'Show me the message and I will look for warning signs. I never call one safe.';
  return 'Sure. Tell me what you can see on your screen and we will go one step at a time.';
}
function sendChat(text) {
  const n = chatN++;
  pushChat({ id: 't' + n, role: 'user', text, final: true });
  const reply = replyFor(text);
  setTimeout(() => pushChat({ id: 'e' + n, role: 'assistant', text: reply, final: false }), 450);
  setTimeout(() => pushChat({ id: 'e' + n, role: 'assistant', text: reply, final: true }), 1400);
}
function ChatView() {
  const uidn = ++uid;
  const thread = h('div', { class: 'al-thread', role: 'log', 'aria-live': 'polite', 'aria-label': 'Conversation' });
  const top = h('div', { class: 'al-chat__top' }, Seg('How we talk', [['voice', 'Talk'], ['text', 'Type']], () => S.chatMode, (v) => set({ chatMode: v, settings: { ...S.settings, textOnly: v === 'text' } })), LevelChip({ variant: 'compact' }));
  const pinned = h('div');
  const input = h('input', { class: 'al-input', id: 'chat-input-' + uidn, type: 'text', autocomplete: 'off' });
  const form = h('form', { class: 'al-composer', onsubmit: (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    send.disabled = true;
    sendChat(text);
  } }, h('label', { class: 'al-sr', for: 'chat-input-' + uidn }, 'Type a message'), input);
  const send = h('button', { class: 'al-btn al-btn--primary', type: 'submit', disabled: true }, 'Send');
  input.addEventListener('input', () => (send.disabled = input.value.trim() === ''));
  form.append(send);
  const root = h('div', { class: 'al-chat' }, top, pinned, thread, form);
  const resting = () => S.phase === 'asleep' || S.phase === 'listening_for_name';
  function draw() {
    input.placeholder = S.chatMode === 'text' ? 'Type your question' : 'Or type here';
    pinned.replaceChildren(...(S.phase === 'live' || S.phase === 'speaking' || S.phase === 'thinking' ? [Stepper(2, 4, 'Make the text bigger')] : []));
    const kids = [];
    if (S.phase === 'error') kids.push(h('div', { class: 'al-banner', role: 'alert' }, h('span', { class: 'al-banner__icon' }, icon('alert')), h('div', { class: 'al-banner__text' }, 'I lost the connection.'), h('button', { class: 'al-btn', type: 'button', onclick: () => set({ phase: 'connecting' }) }, 'Try again')));
    if (chat.messages.length === 0) {
      kids.push(h('div', { class: 'al-empty' }, S.chatMode === 'text' ? h('p', {}, 'Type a message to begin.') : resting()
        ? [h('p', {}, 'Say ', h('strong', {}, `“Hey ${persona()}”`)), h('button', { class: 'al-btn al-btn--lg al-btn--primary', type: 'button', onclick: () => set({ phase: 'connecting' }) }, `Talk to ${persona()}`)]
        : h('p', {}, 'I am listening.')));
    } else chat.messages.forEach((m) => kids.push(h('div', { class: 'al-bubble', 'data-role': m.role, 'data-final': String(m.final) }, m.text)));
    thread.replaceChildren(...kids);
    thread.scrollTop = thread.scrollHeight;
  }
  chatListeners.push(draw);
  on((c) => (c.includes('phase') || c.includes('chatMode') || c.includes('persona')) && draw());
  draw();
  return root;
}

/* ---------- dock ---------- */
function Pill() {
  const wrap = h('span', { class: 'al-orbwrap' });
  const light = h('span', { class: 'al-orbwrap__light', 'aria-hidden': 'true' });
  const drawOrb = () => {
    wrap.replaceChildren(Orb(S.phase, 48), light);
    wrap.dataset.light = lightState();
  };
  drawOrb();
  on((c) => (c.includes('phase') || c.includes('persona') || c.includes('muted')) && drawOrb());
  const chip = LevelChip({ variant: 'compact' });
  const status = h('span', { class: 'al-sr', 'aria-live': 'polite' });
  const st = () => (status.textContent = `${persona()}. ${PHASES[S.phase].name}. ${lightText(lightState())}.`);
  on(st);
  st();
  const main = h('button', { class: 'al-pill__main', type: 'button', 'aria-label': 'Open the panel', title: lightText(lightState()), onclick: () => (expanded.hidden = !expanded.hidden) }, wrap, chip, status);
  return h('div', { class: 'al-dock', role: 'region', 'aria-label': 'Companion, collapsed' }, h('div', { class: 'al-pill' }, main, StopButton(true)));
}
let expanded;
function Panel() {
  const orbHost = h('span', { style: 'display:contents' });
  const drawOrb = () => orbHost.replaceChildren(Orb(S.phase, 48));
  drawOrb();
  const name = h('span', { class: 'al-pill__name' });
  const phase = h('span', { class: 'al-pill__phase' });
  const nameU = () => {
    name.textContent = persona();
    phase.textContent = S.phase === 'error' ? PHASES.error.name : '';
    phase.hidden = S.phase !== 'error';
  };
  nameU();
  const body = h('div', { class: 'al-dock__body', role: 'tabpanel', id: 'dock-panel' });
  const TABS = ['chat', 'progress', 'profile', 'settings'];
  const tabs = TABS.map((t) => h('button', { class: 'al-tab', role: 'tab', type: 'button', 'aria-selected': 'false', onclick: () => set({ tab: t }) }, { chat: 'Chat', progress: 'Progress', profile: 'About you', settings: 'Settings' }[t]));
  const tabsEl = h('div', { class: 'al-tabs', role: 'tablist', 'aria-label': 'Companion sections' }, tabs);
  const chatEl = ChatView();
  const settingsEl = SettingsPanel();
  const progressEl = ProgressView();
  const profileEl = ProfileTab();
  const views = { chat: chatEl, progress: progressEl, profile: profileEl, settings: settingsEl };
  const draw = () => {
    tabs.forEach((b, i) => b.setAttribute('aria-selected', String(TABS[i] === S.tab)));
    body.classList.toggle('al-dock__body--chat', S.tab === 'chat');
    body.replaceChildren(views[S.tab]);
  };
  draw();
  on((c) => {
    if (c.includes('phase') || c.includes('persona')) {
      drawOrb();
      nameU();
    }
    if (c.includes('tab')) draw();
  });
  const aa = h('button', { class: 'al-btn al-btn--quiet al-aa', type: 'button', 'aria-label': 'Easier-to-read font', title: 'Easier-to-read font', 'aria-pressed': 'false', onclick: () => set({ dys: !S.dys }) }, 'Aa');
  on(() => aa.setAttribute('aria-pressed', String(S.dys)));
  const collapse = h('button', { class: 'al-btn al-btn--quiet', type: 'button', 'aria-label': 'Collapse the panel', onclick: () => (expanded.hidden = true) }, icon('up'));
  return h('div', { class: 'al-dock al-dock--panel', role: 'region', 'aria-label': 'Companion panel', 'data-modal-host': '' },
    h('div', { class: 'al-dock__head' }, h('div', { class: 'al-dock__headrow' }, orbHost, h('div', { class: 'al-pill__who', style: 'flex:1;min-width:0' }, name, phase), aa, MuteButton(), collapse)),
    tabsEl, body, h('div', { class: 'al-dock__foot' }, ListeningLight(), StopButton(false)));
}

/* ---------- page ---------- */
function Section(eyebrow, title, desc, ...kids) {
  return h('section', { class: 'pv-section' }, h('div', { class: 'pv-section__head' }, h('p', { class: 'al-eyebrow' }, eyebrow), h('h2', { class: 'al-h1' }, title), desc ? h('p', {}, desc) : null), ...kids);
}
function OrbSection() {
  return h('div', { class: 'pv-orbs' }, Object.entries(PHASES).map(([k, p]) => {
    const host = h('div', { style: 'display:contents' });
    const draw = () => host.replaceChildren(Orb(k, 84));
    draw();
    on((c) => c.includes('persona') && draw());
    return h('div', { class: 'pv-orb' }, host, h('strong', {}, p.name), h('span', {}, p.blurb));
  }));
}
function HeroSection() {
  const chip = LevelChip({ variant: 'hero', fixed: true, level: 2, locked: false });
  const ladder = h('ol', { class: 'pv-ladder' }, [1, 2, 3, 4].map((l) => h('li', { 'data-l': l }, h('strong', {}, `${l}. ${LEVEL_NAMES[l]}`), h('span', {}, LEVEL_BLURBS[l]))));
  const mark = (l) => ladder.querySelectorAll('li').forEach((li) => li.setAttribute('aria-current', String(Number(li.dataset.l) === l)));
  mark(2);
  const go = (l) => {
    chip.render(l, false, true);
    mark(l);
  };
  const replay = () => {
    chip.render(2, false, false);
    mark(2);
    setTimeout(() => go(3), 900);
  };
  const buttons = h('div', { class: 'pv-row' }, h('button', { class: 'al-btn al-btn--primary', type: 'button', onclick: replay }, 'Replay: Walk with me to Nudge me'),
    [1, 2, 3, 4].map((l) => h('button', { class: 'pv-chipbtn', type: 'button', onclick: () => go(l) }, `Go to ${l}`)));
  const stage = h('div', { class: 'pv-stage' }, h('p', { class: 'al-eyebrow' }, 'Visible from across the room'), chip, h('div', { style: 'height:var(--sp-5)' }), ladder);
  let played = false;
  new IntersectionObserver((es) => {
    if (!played && es.some((e) => e.isIntersecting)) {
      played = true;
      setTimeout(replay, 500);
    }
  }, { threshold: 0.6 }).observe(stage);
  return h('div', { class: 'pv-grid', style: 'grid-template-columns:1fr' }, stage, buttons, h('p', { class: 'pv-hint' }, 'The bars are the help I am giving. As you take over, they drain, and the name changes. This is the product in one picture: I am trying to need less.'));
}
function ControlBar() {
  const theme = h('div', { class: 'al-seg', role: 'radiogroup', 'aria-label': 'Theme' });
  const opts = [['light', 'Light'], ['dark', 'Dark'], ['hc', 'Contrast']];
  const btns = opts.map(([v, t]) => h('button', { class: 'al-seg__btn', type: 'button', role: 'radio', 'aria-label': v === 'hc' ? 'High contrast' : t, onclick: () => (v === 'hc' ? set({ hc: true }) : set({ hc: false, themeSetting: v })) }, t));
  btns.forEach((b) => theme.append(b));
  const hcRow = h('div', { class: 'pv-opts__row' }, h('span', { class: 'al-small' }, 'High contrast on'), h('button', { class: 'pv-chipbtn', type: 'button', onclick: () => set({ hcDark: false }) }, 'White'), h('button', { class: 'pv-chipbtn', type: 'button', onclick: () => set({ hcDark: true }) }, 'Black'));
  const u = () => {
    btns.forEach((b, i) => b.setAttribute('aria-checked', String(S.hc ? opts[i][0] === 'hc' : opts[i][0] === S.theme)));
    hcRow.hidden = !S.hc;
    hcRow.querySelectorAll('button').forEach((b, i) => b.setAttribute('aria-pressed', String(S.hcDark === (i === 1))));
  };
  on(u);
  u();
  const toggle = (label, key) => {
    const id = 'o-' + key;
    const input = h('input', { type: 'checkbox', role: 'switch', id, onchange: (e) => set({ [key]: e.target.checked }) });
    input.checked = S[key];
    on(() => (input.checked = S[key]));
    return h('label', { class: 'al-switch', for: id }, h('span', { class: 'al-switch__text' }, h('span', { class: 'al-switch__label' }, label)), input, h('span', { class: 'al-switch__track', 'aria-hidden': 'true' }, h('span', { class: 'al-switch__thumb' })));
  };
  const personaSeg = Seg('Companion', Object.entries(PERSONAS).map(([id, p]) => [id, p.displayName]), () => S.persona, (v) => set({ persona: v }));
  const optsEl = h('div', { class: 'pv-opts', id: 'pv-opts' }, h('div', { class: 'pv-opts__grid' },
    h('div', {}, hcRow, h('div', { class: 'pv-opts__row' }, personaSeg)),
    h('div', {}, toggle('Glass look', 'glass'), toggle('Easier-to-read font', 'dys'), toggle('Big marks on screen', 'big'), toggle('Reduce motion', 'reduce'))));
  const more = h('button', { class: 'al-btn pv-bar__more', type: 'button', 'aria-expanded': 'false', 'aria-controls': 'pv-opts', onclick: (e) => {
    const open = optsEl.dataset.open !== 'true';
    optsEl.dataset.open = String(open);
    e.currentTarget.setAttribute('aria-expanded', String(open));
  } }, 'Options');
  return h('div', { class: 'pv-bar' }, h('div', { class: 'pv-bar__inner' }, theme, more), optsEl);
}

function build() {
  const root = document.getElementById('app');
  const pill = Pill();
  const panel = Panel();
  expanded = h('div', { style: 'display:contents' }, panel);
  const phaseBtns = Object.entries(PHASES).map(([k, p]) => h('button', { class: 'pv-chipbtn', type: 'button', 'aria-pressed': 'false', onclick: () => set({ phase: k }) }, p.name));
  on(() => phaseBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(Object.keys(PHASES)[i] === S.phase))));
  phaseBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(Object.keys(PHASES)[i] === S.phase)));
  const levelBtns = [1, 2, 3, 4].map((l) => h('button', { class: 'pv-chipbtn', type: 'button', 'aria-pressed': 'false', onclick: () => set({ level: l }) }, `Level ${l}`));
  const levelMark = () => levelBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(i + 1 === S.level)));
  levelMark();
  on(levelMark);

  root.append(
    ControlBar(),
    h('div', { class: 'pv-wrap' },
      h('header', { class: 'pv-head' },
        h('div', { class: 'pv-mark' }, Orb('live', 36), 'Alongside'),
        h('h1', {}, 'A patient companion, on your screen.'),
        h('p', {}, 'Everything here is the real interface: the small dock, the level chip, the marks drawn on your screen, and the controls. Tap things. Try the theme and options bar above.')),
      Section('The dock', 'Always there, never in the way', 'A small pill that expands into a panel with four tabs. Type in the chat, or talk. Try Glass look in Options, and Aa for an easier-to-read font.',
        h('div', { class: 'pv-row' }, phaseBtns),
        h('div', { class: 'pv-row' }, h('span', { class: 'al-small' }, 'Help level'), levelBtns),
        h('div', { class: 'pv-desktop' }, pill, expanded)),
      Section('The level chip', 'The moment help fades', 'Walk with me becomes Nudge me. The bars drain as you take over. Designed to read from five metres away.', HeroSection()),
      Section('Presence', 'One orb, seven states', 'Calm, abstract, never a cartoon. It breathes while listening, ripples while speaking and dims while thinking. Shapes and motion differ, so it never relies on colour alone.', OrbSection()),
      Section('On your screen', 'Marks that show on any screen', 'Each line has a white edge and a dark edge, so it stays visible on light and dark screens. Tone is also shown by shape and dashes, for colour-blind readers. Scaled up for this preview.', AnnotationDemo()),
      Section('Captions and helpers', 'Big words, plain status', 'Captions are large and labelled by speaker. Helpers show what they are doing and can always be stopped.',
        h('div', { class: 'pv-grid' },
          h('div', { class: 'pv-card' }, h('h3', { class: 'al-h3' }, 'Captions'), h('div', { class: 'al-captions' }, Caption('user', 'Is this text from my bank?'), Caption('assistant', 'I can check it for warning signs. One moment.'), Caption('assistant', 'I see a deadline and a link', false), Caption('system', 'Captions are on. You can turn them off in Settings.'))),
          h('div', { class: 'pv-card' }, h('h3', { class: 'al-h3' }, 'Helpers'), AgentTray(), h('button', { class: 'al-btn', type: 'button', onclick: startAgent }, 'Start a check')))),
      Section('A real click', 'Asking before it acts', 'Only a click or tap can answer. Nothing a message says, and nothing the model says, can approve an action.', ConfirmDemo()),
      Section('Your profile', 'A file you own', 'One readable file, kept on this computer. Change it, forget any line, or delete it all.', h('div', { class: 'pv-card pv-profilehost', 'data-modal-host': '' }, ProfileTab())),
      Section('Progress', 'Proof you need me less', 'Plain lists and charts you can read at a glance. The hints chart is the point: it should fall.', h('div', { class: 'pv-card' }, ProgressView())),
      h('footer', { class: 'pv-foot' }, 'Alongside design preview. Names are placeholders and set in one constant. All progress figures are example data. Drawn marks are scaled up for the preview.'),
    ),
  );
  set({});
}
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => 0);
const sysDark = matchMedia('(prefers-color-scheme: dark)').matches;
const explicit = document.documentElement.getAttribute('data-theme');
S.themeSetting = explicit === 'dark' || (explicit !== 'light' && sysDark) ? 'dark' : 'light';
build();
