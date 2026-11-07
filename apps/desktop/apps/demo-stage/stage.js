/* Practice Desktop — vanilla JS, no dependencies, no network.
 * Public API: window.__stage (see README.md). All rect output is NORMALISED 0-1000, origin top-left, y down. */
(function () {
  'use strict';

  var Q = new URLSearchParams(location.search);
  var truthy = function (k) { return /^(1|true|yes)$/i.test(Q.get(k) || ''); };
  var STILL = truthy('still');
  var DEBUG = truthy('debug');
  var SCALES = [1, 1.25, 1.5, 1.75, 2];
  var SCALE_NAMES = ['Default', 'Large', 'Larger', 'Very large', 'Largest'];
  var FLOWS = window.STAGE_FLOWS || {};
  var APPS = { video: { name: 'VideoChat', icon: 'camera' }, messages: { name: 'Messages', icon: 'chat' }, settings: { name: 'Settings', icon: 'gear' } };

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var icon = function (n, cls) { return '<svg class="ic' + (cls ? ' ' + cls : '') + '" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; };
  var r1 = function (n) { return Math.round(n * 10) / 10; };

  /* ------------------------------------------------------------------ data */
  var CONTACTS = [
    { id: 'dave', name: 'Dave Morgan', rel: 'Neighbour', online: false, color: '#b45309', note: 'Last call: 3 weeks ago' },
    { id: 'lily', name: 'Lily', rel: 'Granddaughter', online: true, color: '#0f766e', note: 'Last call: Sunday, 23 minutes' },
    { id: 'priya', name: 'Priya Shah', rel: 'Friend', online: true, color: '#7c3aed', note: 'Last call: last month' },
    { id: 'surgery', name: 'Riverside Surgery', rel: 'Reception', online: false, color: '#0369a1', note: 'No calls yet' },
    { id: 'rosa', name: 'Rosa Bell', rel: 'Book club', online: false, color: '#be185d', note: 'Last call: 2 months ago' },
    { id: 'tom', name: 'Tom (plumber)', rel: 'Work', online: false, color: '#475569', note: 'No calls yet' }
  ];
  var contactById = function (id) { return CONTACTS.filter(function (c) { return c.id === id; })[0] || null; };
  var initials = function (name) { return name.replace(/[()]/g, '').split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase(); };

  /* Genuine conversations are in the inbox from the start; deliverGenuine(i) re-delivers one as a fresh unread text. */
  var GENUINE_ORDER = ['surgery', 'lily', 'family', 'pharmacy'];
  var GENUINE = {
    surgery: { name: 'Riverside Surgery', sub: 'Appointments', color: '#0369a1', history: [],
      incoming: 'Reminder: you have an appointment with Dr Okafor on Tuesday 4 November at 10:20. Please arrive 5 minutes early. If you cannot attend, call the surgery on the number on your appointment card.', time: 'Yesterday' },
    lily: { name: 'Lily', sub: 'Granddaughter', color: '#0f766e', history: [{ from: 'me', text: 'Hello love, how was your week?', time: 'Thu 18:02' }],
      incoming: 'Hi Gran! Are you free for a video call on Sunday at 4? I want to show you the new flat. Love you x', time: 'Thu' },
    family: { name: 'Family Chat', sub: 'Dave, Jo, Mum and 2 others', color: '#b45309', history: [{ from: 'them', who: 'Jo', text: 'Photos from the garden party are up!', time: 'Tue 20:15' }],
      incoming: 'Dave: Lunch at ours on Saturday, 1pm. Who is bringing the trifle?', time: 'Wed' },
    pharmacy: { name: 'Greenfield Pharmacy', sub: 'Prescriptions', color: '#15803d', history: [],
      incoming: 'Your prescription is ready to collect from Greenfield Pharmacy. We are open Mon to Sat, 9am to 6pm. Please bring your name and date of birth.', time: 'Mon' }
  };
  var SCAMS = {
    scam: { name: 'Aldermoor Bank', sub: '+44 7700 900482', color: '#7f1d1d',
      text: 'URGENT: Aldermoor Bank. Your account has been LOCKED after suspicious activity. Verify your identity within 2 hours or your money will be frozen. Verify now: https://aldermoor-bank.secure-verify.co/login' },
    scam_parcel: { name: 'Parcel Courier', sub: '+44 7700 900617', color: '#9a3412',
      text: 'We tried to deliver your parcel today but nobody was home. Pay a £1.45 re-delivery fee within 24 hours or it will be returned: https://parcel-redelivery-uk.top/pay' },
    scam_family: { name: 'Unknown number', sub: '+44 7700 900755', color: '#52525b',
      text: 'Hi Mum, I dropped my phone in water. This is my new number, please delete the old one. Can you send £480 to this account right now? It is urgent, I will explain later x' }
  };
  var SCAM_ALIAS = { '0': 'scam', bank: 'scam', scam: 'scam', '1': 'scam_parcel', parcel: 'scam_parcel', 'scam-parcel': 'scam_parcel', scam_parcel: 'scam_parcel', '2': 'scam_family', family: 'scam_family', 'scam-family': 'scam_family', scam_family: 'scam_family' };

  /* Settings-style rows. Every row gets data-ground-id = prefix + id. */
  var PANELS = [
    { id: 'general', label: 'General', icon: 'sliders', kw: 'language time clock name about region', rows: [
      { t: 'select', id: 'language', label: 'Language', opts: ['English (UK)', 'English (US)', 'Cymraeg'] },
      { t: 'select', id: 'time_format', label: 'Time format', opts: ['12-hour', '24-hour'] },
      { t: 'text', id: 'device_name', label: 'Device name', value: 'Practice Desktop' },
      { t: 'info', id: 'about', label: 'About', value: 'Practice Desktop 1.0 - for learning only' }
    ] },
    { id: 'display', label: 'Display', icon: 'monitor', kw: 'text size font bigger larger smaller zoom brightness dark theme contrast screen', custom: true },
    { id: 'sound', label: 'Sound', icon: 'volume', kw: 'volume speaker mute audio', rows: [
      { t: 'slider', id: 'volume', label: 'Volume', min: 0, max: 100, value: 60 },
      { t: 'select', id: 'output', label: 'Play sound through', opts: ['Built-in speakers', 'Headphones'] },
      { t: 'switch', id: 'mute', label: 'Mute all sounds', value: false }
    ] },
    { id: 'notifications', label: 'Notifications', icon: 'bell', kw: 'alerts banners messages reminders', rows: [
      { t: 'switch', id: 'messages', label: 'Messages', desc: 'Show a banner when a text arrives', value: true },
      { t: 'switch', id: 'videochat', label: 'VideoChat', desc: 'Show a banner for incoming calls', value: true },
      { t: 'switch', id: 'reminders', label: 'Reminders', value: true }
    ] },
    { id: 'privacy', label: 'Privacy', icon: 'shield', kw: 'location camera microphone data permissions', rows: [
      { t: 'switch', id: 'location', label: 'Location', desc: 'Let apps see where you are', value: false },
      { t: 'switch', id: 'camera_access', label: 'Camera access', value: true },
      { t: 'switch', id: 'microphone_access', label: 'Microphone access', value: true },
      { t: 'switch', id: 'share_usage', label: 'Share usage data', desc: 'Help improve this desktop', value: false }
    ] },
    { id: 'advanced', label: 'Advanced', icon: 'warning', kw: 'developer network proxy reset cache expert', custom: true }
  ];
  var DISPLAY_ROWS = [
    { t: 'slider', id: 'brightness', label: 'Brightness', min: 30, max: 100, value: 100, input: 'brightness' },
    { t: 'switch', id: 'dark_theme', label: 'Dark theme', desc: 'Light writing on a dark background', value: false },
    { t: 'switch', id: 'high_contrast', label: 'High contrast', desc: 'Stronger colours and borders', value: false },
    { t: 'switch', id: 'night_light', label: 'Night light', desc: 'Warmer colours in the evening', value: false }
  ];
  var ADVANCED_ROWS = [
    { t: 'switch', id: 'developer_mode', label: 'Developer mode', value: false },
    { t: 'switch', id: 'remote_access', label: 'Allow remote access', desc: 'Let other computers connect to this one', value: false },
    { t: 'switch', id: 'disable_security', label: 'Turn off security checks', value: false },
    { t: 'text', id: 'proxy', label: 'Network proxy', value: '' },
    { t: 'text', id: 'dns', label: 'DNS server', value: 'Automatic' }
  ];
  var VIDEO_SETTINGS_ROWS = [
    { t: 'select', id: 'camera', label: 'Camera', opts: ['Built-in camera', 'External camera'] },
    { t: 'select', id: 'microphone', label: 'Microphone', opts: ['Built-in microphone', 'Headset microphone'] },
    { t: 'switch', id: 'blur', label: 'Blur my background', value: false },
    { t: 'switch', id: 'hw_accel', label: 'Hardware acceleration', desc: 'Use the graphics chip for video', value: true },
    { t: 'switch', id: 'autostart', label: 'Start VideoChat when I sign in', value: false },
    { t: 'switch', id: 'ring', label: 'Ring for incoming calls', value: true },
    { t: 'button', id: 'sign_out', label: 'Sign out', act: 'video.practice' }
  ];

  /* ------------------------------------------------------------------ state */
  var S, ringT = null, tickT = null, toastT = null, clockT = null, events = [], listeners = [], seq = 0, lastFocusId = null, threadKey = '';
  var genuineCursor = 0;

  function defaultToggles() {
    var t = {};
    var add = function (prefix, rows) { rows.forEach(function (r) { if (r.t === 'switch') t[prefix + r.id] = !!r.value; }); };
    PANELS.forEach(function (p) { if (p.rows) add('settings.' + p.id + '.', p.rows); });
    add('settings.display.', DISPLAY_ROWS); add('settings.advanced.', ADVANCED_ROWS); add('video.settings.', VIDEO_SETTINGS_ROWS);
    return t;
  }
  function freshState() {
    var convs = {};
    GENUINE_ORDER.forEach(function (id) {
      var g = GENUINE[id];
      convs[id] = { unread: false, time: g.time, msgs: g.history.concat([{ from: 'them', who: g.who, text: g.incoming, time: g.time }]), blocked: false, reported: false };
    });
    var s = {
      route: 'desktop', app: null, running: [], maxed: {}, textStep: 0, brightness: 100, toggles: defaultToggles(),
      video: { view: 'contacts', selected: null, search: '', preMic: true, preCamera: true, mic: true, camera: true, callState: 'idle', seconds: 0, callsStarted: 0, lastDuration: 0, withContact: null },
      msg: { order: GENUINE_ORDER.slice(), convs: convs, selected: null, menuOpen: false, search: '', delivered: [], linkClicked: false, deleted: [], lastSent: null },
      set: { section: 'general', search: '' },
      toast: null, modal: null, menu: false, focus: null
    };
    var sc = parseInt(Q.get('scale'), 10);
    if (sc >= 0 && sc < SCALES.length) s.textStep = sc;
    if (Q.get('theme') === 'dark') s.toggles['settings.display.dark_theme'] = true;
    if (Q.get('contrast') === 'high') s.toggles['settings.display.high_contrast'] = true;
    // Interactive demo (?seedscam=1): the Aldermoor Bank scam text is already in the inbox, unread (the Messages icon shows the badge).
    if (Q.get('seedscam') === '1') {
      s.msg.convs.scam = { unread: true, time: 'Now', msgs: [{ from: 'them', text: SCAMS.scam.text, time: '10:42' }], blocked: false, reported: false };
      s.msg.order = ['scam'].concat(GENUINE_ORDER);
      s.msg.delivered = ['scam'];
    }
    return s;
  }

  /* ------------------------------------------------------------------ events */
  function emit(type, detail) {
    var ev = { seq: ++seq, t: Date.now(), type: type, route: S ? S.route : null };
    if (detail) Object.keys(detail).forEach(function (k) { ev[k] = detail[k]; });
    events.push(ev);
    if (events.length > 500) events.shift();
    listeners.slice().forEach(function (fn) { try { fn(ev); } catch (e) { console.error(e); } });
    try { window.dispatchEvent(new CustomEvent('stage:event', { detail: ev })); } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------------ build static pieces */
  function rowHtml(prefix, r) {
    var gid = prefix + r.id;
    var text = '<div class="r-text"><div class="r-label">' + esc(r.label) + '</div>' + (r.desc ? '<div class="r-desc">' + esc(r.desc) + '</div>' : '') + '</div>';
    var ctl = '';
    if (r.t === 'switch') ctl = '<button type="button" role="switch" class="switch" aria-checked="false" aria-label="' + esc(r.label) + '" data-act="switch" data-key="' + gid + '" data-ground-id="' + gid + '"><span class="knob"></span></button>';
    else if (r.t === 'select') ctl = '<select aria-label="' + esc(r.label) + '" data-ground-id="' + gid + '">' + r.opts.map(function (o) { return '<option>' + esc(o) + '</option>'; }).join('') + '</select>';
    else if (r.t === 'text') ctl = '<input type="text" aria-label="' + esc(r.label) + '" value="' + esc(r.value || '') + '" data-ground-id="' + gid + '">';
    else if (r.t === 'slider') ctl = '<input type="range" min="' + r.min + '" max="' + r.max + '" value="' + r.value + '" aria-label="' + esc(r.label) + '"' + (r.input ? ' data-input="' + r.input + '"' : '') + ' data-ground-id="' + gid + '" style="width:min(16rem,45%)">';
    else if (r.t === 'info') ctl = '<span class="muted" data-ground-id="' + gid + '">' + esc(r.value) + '</span>';
    else if (r.t === 'button') ctl = '<button type="button" class="btn" data-act="' + r.act + '" data-label="' + esc(r.label) + '" data-ground-id="' + gid + '">' + esc(r.label) + '</button>';
    if (r.t === 'button') return '<div class="row"><div class="r-text"><div class="r-label">Account</div><div class="r-desc">Signed in as the practice user</div></div>' + ctl + '</div>';
    return '<div class="row">' + text + ctl + '</div>';
  }
  function build() {
    $('#vc-settings-rows').innerHTML = VIDEO_SETTINGS_ROWS.map(function (r) { return rowHtml('video.settings.', r); }).join('');

    $('#set-nav-list').innerHTML = PANELS.map(function (p) {
      return '<button type="button" class="nav-item" data-act="set.nav" data-id="' + p.id + '" data-kw="' + esc(p.label + ' ' + p.kw).toLowerCase() + '" data-ground-id="settings.nav.' + p.id + '">' + icon(p.icon) + '<span>' + esc(p.label) + '</span></button>';
    }).join('');

    var panels = PANELS.map(function (p) {
      var inner;
      if (p.id === 'display') {
        inner =
          '<div class="card">' +
            '<div class="ts-head"><div><h3 data-ground-id="settings.text_size.heading">Text size</h3><p class="muted">Make the words on the screen bigger or smaller.</p></div>' +
            '<div class="ts-value" id="ts-value" data-ground-id="settings.text_size.value" data-kind="block">100% · Default</div></div>' +
            '<div class="ts-row">' +
              '<button type="button" class="ts-btn" data-act="set.smaller" data-ground-id="settings.text_smaller" aria-label="Make text smaller"><span class="ts-a small">A</span><span class="ts-l">Smaller</span></button>' +
              '<input type="range" id="ts-slider" min="0" max="4" step="1" value="0" aria-label="Text size" data-input="textsize" data-ground-id="settings.text_size_slider">' +
              '<button type="button" class="ts-btn" data-act="set.larger" data-ground-id="settings.text_larger" aria-label="Make text bigger" data-desc="Button with a big letter A and the word Larger, to the right of the slider inside the Text size card"><span class="ts-a big">A</span><span class="ts-l">Larger</span></button>' +
            '</div>' +
            '<div class="preview" data-ground-id="settings.text_size.preview" data-kind="block"><div class="p-label">Preview</div><p>Your appointment is on Tuesday at 10:20. Please arrive five minutes early.</p></div>' +
          '</div>' +
          '<div class="card">' + DISPLAY_ROWS.map(function (r) { return rowHtml('settings.display.', r); }).join('') + '</div>';
      } else if (p.id === 'advanced') {
        inner =
          '<div class="banner-warn" data-ground-id="settings.advanced.warning" data-kind="block">' + icon('warning') + '<span>Careful: these settings are for experts. Changing them can stop things working.</span></div>' +
          '<div class="card">' + ADVANCED_ROWS.map(function (r) { return rowHtml('settings.advanced.', r); }).join('') +
          '<div class="row-actions"><button type="button" class="btn" data-act="set.clear" data-ground-id="settings.advanced.clear_cache">Clear cache</button>' +
          '<button type="button" class="btn danger" data-act="set.reset" data-ground-id="settings.advanced.reset_all">Reset all settings…</button></div></div>';
      } else {
        inner = '<div class="card">' + p.rows.map(function (r) { return rowHtml('settings.' + p.id + '.', r); }).join('') + '</div>';
      }
      return '<section class="panel" data-panel="' + p.id + '" hidden><h2 data-ground-id="settings.' + p.id + '.heading">' + esc(p.label) + '</h2>' + inner + '</section>';
    }).join('');
    $('#set-panels').innerHTML = panels;
  }

  /* ------------------------------------------------------------------ actions on state */
  function resetState() {
    clearTimeout(ringT); clearInterval(tickT); clearTimeout(toastT); ringT = tickT = toastT = null;
    S = freshState();
    threadKey = '';
    $('#compose-input').value = '';
    $('#vc-search').value = ''; $('#msg-search').value = ''; $('#set-search').value = '';
  }
  function openApp(app) {
    if (S.running.indexOf(app) < 0) S.running.push(app);
    S.app = app; S.menu = false; S.modal = null;
    if (app === 'messages') dismissToast();
    emit('open_app', { app: app });
  }
  function closeApp(app) {
    S.running = S.running.filter(function (a) { return a !== app; });
    if (S.app === app) S.app = null;
    if (app === 'video') { if (S.video.callState !== 'idle') endCall(); S.video.view = 'contacts'; S.video.selected = null; }
    if (app === 'messages') { S.msg.selected = null; S.msg.menuOpen = false; }
    if (app === 'settings') S.set.section = 'general';
    S.maxed[app] = false;
    emit('close_app', { app: app });
  }
  function selectContact(id) {
    if (!contactById(id)) return;
    S.video.selected = id; S.video.view = 'contacts';
    emit('select_contact', { contact: id });
  }
  function startPrecall(camOn) {
    S.video.view = 'precall'; S.video.preCamera = camOn; S.video.preMic = true; S.focus = 'video.precall.join';
    emit('precall', { contact: S.video.selected });
  }
  function startCall() {
    var v = S.video;
    v.view = 'call'; v.callState = 'ringing'; v.seconds = 0; v.mic = v.preMic; v.camera = v.preCamera; v.withContact = v.selected; v.callsStarted++;
    emit('call_started', { contact: v.selected });
    clearTimeout(ringT);
    ringT = setTimeout(function () { connectCall(); render(); }, STILL ? 900 : 2200);
  }
  function connectCall() {
    var v = S.video;
    if (v.callState !== 'ringing') return;
    clearTimeout(ringT);
    v.callState = 'connected'; v.seconds = STILL ? 12 : 0;
    clearInterval(tickT);
    tickT = setInterval(function () { if (S.video.callState === 'connected' && !STILL) { S.video.seconds++; renderTimers(); } }, 1000);
    emit('call_connected', { contact: v.withContact });
  }
  function endCall() {
    var v = S.video;
    clearTimeout(ringT); clearInterval(tickT);
    var was = v.callState;
    v.lastDuration = v.seconds; v.callState = 'idle';
    if (v.view === 'call') { v.view = 'ended'; S.focus = 'video.ended.back'; }
    if (was !== 'idle') emit('call_ended', { contact: v.withContact, seconds: v.lastDuration });
  }
  function setTextStep(n, how) {
    n = Math.max(0, Math.min(SCALES.length - 1, n | 0));
    if (n === S.textStep) return;
    S.textStep = n;
    emit('text_size', { step: n, percent: Math.round(SCALES[n] * 100), via: how || 'api' });
  }
  function dismissToast() { S.toast = null; clearTimeout(toastT); }
  function showToast(conv, title, text) {
    S.toast = { conv: conv, title: title, text: text };
    clearTimeout(toastT);
    if (!STILL) toastT = setTimeout(function () { S.toast = null; render(); }, 20000);
  }
  function convMeta(id) { return GENUINE[id] || SCAMS[id]; }
  function bumpConv(id, time) {
    S.msg.order = [id].concat(S.msg.order.filter(function (x) { return x !== id; }));
    var c = S.msg.convs[id]; c.time = time;
    c.unread = !(S.app === 'messages' && S.msg.selected === id);
  }
  function deliverScam(variant) {
    var key = SCAM_ALIAS[String(variant == null ? 0 : variant).toLowerCase()] || 'scam';
    var d = SCAMS[key];
    var c = S.msg.convs[key];
    if (!c) c = S.msg.convs[key] = { unread: true, time: 'Now', msgs: [{ from: 'them', text: d.text, time: '10:42' }], blocked: false, reported: false };
    S.msg.deleted = S.msg.deleted.filter(function (x) { return x !== key; });
    bumpConv(key, 'Now');
    S.msg.delivered.push(key);
    showToast(key, d.name, d.text);
    emit('deliver', { kind: 'scam', conv: key });
    render();
    return key;
  }
  function deliverGenuine(i) {
    var key = typeof i === 'string' && GENUINE[i] ? i : GENUINE_ORDER[((parseInt(i, 10) || 0) % GENUINE_ORDER.length + GENUINE_ORDER.length) % GENUINE_ORDER.length];
    var g = GENUINE[key];
    var c = S.msg.convs[key];
    S.msg.deleted = S.msg.deleted.filter(function (x) { return x !== key; });
    c.blocked = false;
    bumpConv(key, 'Now');
    S.msg.delivered.push(key);
    showToast(key, g.name, g.incoming);
    emit('deliver', { kind: 'genuine', conv: key });
    render();
    return key;
  }
  function openConv(id) {
    if (!S.msg.convs[id]) return;
    S.msg.selected = id; S.msg.menuOpen = false; S.msg.convs[id].unread = false;
    if (S.toast && S.toast.conv === id) dismissToast();
    emit('open_conversation', { conv: id });
  }
  function modal(title, body, buttons, opener) {
    S.modal = { title: title, body: body, opener: opener || lastFocusId, buttons: buttons || [{ id: 'modal.ok', label: 'OK', kind: 'primary', act: 'modal.close' }] };
    S.focus = (S.modal.buttons[S.modal.buttons.length - 1].id);
    emit('modal', { title: title });
  }
  function practiceModal(label) { modal(label, 'This is just for show in the practice desktop. Nothing happens here.'); }

  /* ------------------------------------------------------------------ click actions */
  var ACT = {
    'desk.open': function (el) { openApp(el.dataset.app); },
    'desk.decoy': function (el) { modal(el.dataset.label, 'This app is not part of the practice desktop.'); },
    'desk.menu': function () { S.menu = !S.menu; },
    'desk.menu.open': function (el) { openApp(el.dataset.app); },
    'task.focus': function (el) { openApp(el.dataset.app); },
    'win.min': function () { S.app = null; emit('minimise'); },
    'win.max': function (el) { S.maxed[el.dataset.app] = !S.maxed[el.dataset.app]; },
    'win.close': function (el) { closeApp(el.dataset.app); },
    'toast.open': function () { var c = S.toast && S.toast.conv; openApp('messages'); if (c) openConv(c); },
    'toast.dismiss': function () { dismissToast(); emit('toast_dismissed'); },
    'modal.close': function () { closeModal(); },
    'switch': function (el) { toggleSwitch(el.dataset.key); },

    'video.restore': function () { openApp('video'); },
    'video.contacts': function () { S.video.view = 'contacts'; },
    'video.select': function (el) { selectContact(el.dataset.id); },
    'video.start': function () { startPrecall(true); },
    'video.voice': function () { startPrecall(false); },
    'video.cancel': function () { S.video.view = 'contacts'; },
    'video.preCam': function () { S.video.preCamera = !S.video.preCamera; },
    'video.preMic': function () { S.video.preMic = !S.video.preMic; },
    'video.join': function () { startCall(); },
    'video.mic': function () { S.video.mic = !S.video.mic; emit('mic', { on: S.video.mic }); },
    'video.cam': function () { S.video.camera = !S.video.camera; emit('camera', { on: S.video.camera }); },
    'video.hangup': function () { endCall(); },
    'video.again': function () { startPrecall(true); },
    'video.settings': function () { S.video.view = 'settings'; },
    'video.practice': function (el) { practiceModal(el.dataset.label || 'Not available'); },

    'msg.open': function (el) { openConv(el.dataset.id); },
    'msg.new': function () { practiceModal('New message'); },
    'msg.menu': function () { S.msg.menuOpen = !S.msg.menuOpen; },
    'msg.report': function () { var c = S.msg.convs[S.msg.selected]; if (c) { c.reported = true; c.blocked = true; } S.msg.menuOpen = false; S.focus = 'messages.thread.menu'; emit('report_junk', { conv: S.msg.selected }); },
    'msg.block': function () { var c = S.msg.convs[S.msg.selected]; if (c) c.blocked = true; S.msg.menuOpen = false; S.focus = 'messages.thread.menu'; emit('block', { conv: S.msg.selected }); },
    'msg.delete': function () {
      var id = S.msg.selected; S.msg.order = S.msg.order.filter(function (x) { return x !== id; }); S.msg.deleted.push(id);
      S.msg.selected = null; S.msg.menuOpen = false; S.focus = 'messages.new'; emit('delete_conversation', { conv: id });
    },
    'msg.link': function (el, e) {
      e.preventDefault(); S.msg.linkClicked = true; emit('link_clicked', { conv: el.dataset.conv });
      modal('Practice link', 'In real life this would open a web page. Nothing was opened, because this is a practice desktop.');
    },

    'set.nav': function (el) { S.set.section = el.dataset.id; S.focus = 'settings.' + el.dataset.id + '.heading'; emit('settings_section', { section: el.dataset.id }); },
    'set.smaller': function () { setTextStep(S.textStep - 1, 'button'); },
    'set.larger': function () { setTextStep(S.textStep + 1, 'button'); },
    'set.clear': function () { modal('Cache cleared', 'Temporary files were removed (practice desktop: nothing really changed).'); },
    'set.reset': function () {
      modal('Reset all settings?', 'This puts every setting back to how it was when the desktop was new, including the text size.', [
        { id: 'modal.cancel', label: 'Cancel', kind: '', act: 'modal.close' },
        { id: 'modal.confirm', label: 'Reset everything', kind: 'danger', act: 'set.reset_confirm' }
      ]);
      S.focus = 'modal.cancel';
    },
    'set.reset_confirm': function () { var step = S.textStep; S.toggles = defaultToggles(); S.brightness = 100; S.textStep = 0; closeModal(); emit('settings_reset', { fromTextStep: step }); }
  };
  function closeModal() {
    var op = S.modal && S.modal.opener; S.modal = null; if (op) S.focus = op;
  }
  function toggleSwitch(key) {
    S.toggles[key] = !S.toggles[key];
    emit('switch', { key: key, on: S.toggles[key] });
  }

  document.addEventListener('click', function (e) {
    var gt = e.target.closest ? e.target.closest('[data-ground-id]') : null;
    var a = e.target.closest ? e.target.closest('[data-act]') : null;
    if (S.menu && !e.target.closest('#menu-root') && !(a && a.dataset.act === 'desk.menu')) S.menu = false;
    if (S.msg.menuOpen && !e.target.closest('#th-menu') && !e.target.closest('#th-menu-btn')) S.msg.menuOpen = false;
    var vw = window.innerWidth, vh = window.innerHeight;
    emit('click', { id: gt ? gt.dataset.groundId : null, act: a ? a.dataset.act : null, x: r1(e.clientX / vw * 1000), y: r1(e.clientY / vh * 1000) });
    if (a && ACT[a.dataset.act]) ACT[a.dataset.act](a, e);
    render();
  });
  document.addEventListener('input', function (e) {
    var t = e.target, kind = t.getAttribute && t.getAttribute('data-input');
    if (t.id === 'vc-search') { S.video.search = t.value; }
    else if (t.id === 'msg-search') { S.msg.search = t.value; }
    else if (t.id === 'set-search') { S.set.search = t.value; }
    else if (kind === 'textsize') { setTextStep(parseInt(t.value, 10), 'slider'); }
    else if (kind === 'brightness') { S.brightness = parseInt(t.value, 10); emit('brightness', { value: S.brightness }); }
    else return;
    render();
  });
  document.addEventListener('submit', function (e) {
    if (e.target.id !== 'compose') return;
    e.preventDefault();
    var inp = $('#compose-input'), txt = inp.value.trim();
    if (!txt || !S.msg.selected) return;
    S.msg.convs[S.msg.selected].msgs.push({ from: 'me', text: txt, time: 'Now' });
    S.msg.lastSent = { conv: S.msg.selected, text: txt };
    inp.value = '';
    emit('message_sent', { conv: S.msg.selected, text: txt });
    render();
  });
  document.addEventListener('focusin', function (e) { var g = e.target.closest && e.target.closest('[data-ground-id]'); if (g) lastFocusId = g.dataset.groundId; });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (S.modal) closeModal(); else if (S.msg.menuOpen) { S.msg.menuOpen = false; S.focus = 'messages.thread.menu'; } else if (S.menu) { S.menu = false; S.focus = 'desk.menu'; } else return;
      render(); return;
    }
    if (e.key === 'Tab' && S.modal) {
      var f = $$('#modal-root button'); if (!f.length) return;
      var i = f.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { f[f.length - 1].focus(); e.preventDefault(); }
      else if (!e.shiftKey && i === f.length - 1) { f[0].focus(); e.preventDefault(); }
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
    var t = e.target, typing = t && (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable || (t.tagName === 'INPUT' && !/^(range|checkbox|radio|button)$/.test(t.type)));
    if (typing) return;
    var k = e.key.toLowerCase();
    if (k === 's') { deliverScam(); }
    else if (k === 'g') { deliverGenuine(genuineCursor++); }
    else if (k === 'r' && e.shiftKey) { api.reset(); }
    else if (k === 'd') { api.debug(!document.getElementById('debug-layer').dataset.on); }
    else if (k === 'f') { try { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen(); } catch (err) { /* ignore */ } }
  });

  /* ------------------------------------------------------------------ rendering */
  function setHidden(el, hide) { if (el.hidden !== hide) el.hidden = hide; }
  function setHtml(el, html) { if (el.__html !== html) { el.innerHTML = html; el.__html = html; } }
  function setText(el, txt) { if (el.textContent !== txt) el.textContent = txt; }
  var fmt = function (s) { var m = Math.floor(s / 60), x = s % 60; return (m < 10 ? '0' : '') + m + ':' + (x < 10 ? '0' : '') + x; };

  function render() {
    var active = document.activeElement;
    var fid = S.focus || (active && active.getAttribute && active.getAttribute('data-ground-id'));
    var root = document.documentElement;
    root.style.setProperty('--text-scale', String(SCALES[S.textStep]));
    root.dataset.theme = S.toggles['settings.display.dark_theme'] ? 'dark' : 'light';
    root.dataset.contrast = S.toggles['settings.display.high_contrast'] ? 'high' : 'normal';
    root.style.setProperty('--dim', String(((100 - S.brightness) / 100 * 0.75).toFixed(3)));
    root.style.setProperty('--night', S.toggles['settings.display.night_light'] ? '1' : '0');

    renderChrome(); renderVideo(); renderMessages(); renderSettings(); renderOverlays();
    $$('[role="switch"][data-key]').forEach(function (b) { var on = String(!!S.toggles[b.dataset.key]); if (b.getAttribute('aria-checked') !== on) b.setAttribute('aria-checked', on); });

    if (fid) {
      var target = $('[data-ground-id="' + fid + '"]');
      if (target && !target.hidden && target !== document.activeElement && (S.focus || !document.body.contains(active) || active === document.body)) {
        try { target.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
      }
    }
    S.focus = null;
    schedDebug();
  }

  function renderChrome() {
    setText($('#tb-title'), S.app ? APPS[S.app].name : 'Desktop');
    $$('.window').forEach(function (w) { setHidden(w, S.app !== w.dataset.app); w.classList.toggle('max', !!S.maxed[w.dataset.app]); });
    setHtml($('#tb-tasks'), S.running.map(function (a) {
      return '<button type="button" class="tb-task' + (S.app === a ? ' active' : '') + '" data-act="task.focus" data-app="' + a + '" data-ground-id="desk.task.' + a + '">' + icon(APPS[a].icon) + '<span>' + APPS[a].name + '</span></button>';
    }).join(''));
    var inCall = S.video.callState !== 'idle' && S.app !== 'video';
    setHidden($('#callpill'), !inCall);
    renderTimers();
    var unread = S.msg.order.filter(function (id) { return S.msg.convs[id].unread; }).length;
    var b = $('#badge-messages'); setHidden(b, unread === 0); setText(b, String(unread));
    $('#desk-icons').querySelector('[data-ground-id="desk.icon.messages"]').setAttribute('aria-label', 'Messages' + (unread ? ', ' + unread + ' unread' : ''));
    updateClock();
  }
  function renderTimers() {
    var v = S.video;
    setText($('#call-timer'), v.callState === 'ringing' ? '00:00' : fmt(v.seconds));
    setText($('#callpill-text'), (v.callState === 'ringing' ? 'Calling' : 'In call ' + fmt(v.seconds)) + ' - return to VideoChat');
  }
  function updateClock() {
    var el = $('#clock');
    if (STILL) { setText(el, '10:42'); return; }
    var d = new Date(); setText(el, ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2));
  }

  function renderVideo() {
    var v = S.video, c = contactById(v.selected), withC = contactById(v.withContact) || c || contactById('lily');
    $$('#win-video [data-view]').forEach(function (s) { setHidden(s, s.dataset.view !== v.view); });
    $$('#win-video .rail-btn').forEach(function (b) {
      var id = b.dataset.groundId;
      b.classList.toggle('active', (id === 'video.settings' && v.view === 'settings') || (id === 'video.rail.contacts' && v.view !== 'settings'));
    });
    var q = v.search.trim().toLowerCase();
    setHtml($('#vc-list'), CONTACTS.filter(function (x) { return !q || (x.name + ' ' + x.rel).toLowerCase().indexOf(q) >= 0; }).map(function (x) {
      return '<button type="button" class="contact" role="option" aria-selected="' + (x.id === v.selected) + '" data-act="video.select" data-id="' + x.id + '" data-ground-id="video.contact.' + x.id + '">' +
        '<span class="avatar" style="--c:' + x.color + '" aria-hidden="true">' + initials(x.name) + '</span>' +
        '<span class="c-text"><div class="c-name">' + esc(x.name) + '</div><div class="c-sub">' + esc(x.rel) + (x.online ? ' · Online' : '') + '</div></span>' +
        '<span class="dot' + (x.online ? ' on' : '') + '" title="' + (x.online ? 'Online' : 'Offline') + '"></span></button>';
    }).join('') || '<p class="muted" style="padding:1rem">No contacts match.</p>');
    setHtml($('#vc-detail'), c ?
      '<span class="avatar xl" style="--c:' + c.color + '" data-ground-id="video.detail.avatar" data-kind="media">' + initials(c.name) + '</span>' +
      '<h2 data-ground-id="video.detail.name">' + esc(c.name) + '</h2>' +
      '<p class="d-sub" data-ground-id="video.detail.relation">' + esc(c.rel) + (c.online ? ' · Online now' : ' · Offline') + '</p>' +
      '<p class="d-note">' + esc(c.note) + '</p>' +
      '<div class="d-actions">' +
        '<button type="button" class="btn good big" data-act="video.start" data-ground-id="video.start_call" data-desc="Large green button reading Start call with a camera icon, in the right-hand pane below the contact name">' + icon('camera') + 'Start call</button>' +
        '<button type="button" class="btn big" data-act="video.voice" data-ground-id="video.detail.voice_only" aria-label="Voice call only" title="Voice call only">' + icon('phone') + '</button>' +
        '<button type="button" class="btn big" data-act="video.practice" data-label="Message" data-ground-id="video.detail.message">Message</button>' +
      '</div>'
      : '<svg class="ic big muted" aria-hidden="true"><use href="#i-users"/></svg><p class="muted" data-ground-id="video.detail.empty">Select a contact to see more.</p>');

    setText($('#pre-sub'), 'Call with ' + withC.name);
    setText($('#pre-heading'), 'Ready to join?');
    setText($('#pre-cam-label'), v.preCamera ? 'Camera is on' : 'Camera is off');
    $('#pre-cam-label').parentNode.style.filter = v.preCamera ? '' : 'grayscale(1) brightness(.45)';
    setText($('#call-name'), withC.name);
    setText($('#main-label').lastChild, withC.name);
    setText($('#ringing-text'), 'Calling ' + withC.name + '…');
    setText($('#call-status'), v.callState === 'ringing' ? 'Calling…' : v.callState === 'connected' ? 'Connected' : '');
    setHidden($('#ringing'), v.callState !== 'ringing');
    $('#win-video [data-ground-id="video.precall.camera"]').setAttribute('aria-checked', String(v.preCamera));
    $('#win-video [data-ground-id="video.precall.mic"]').setAttribute('aria-checked', String(v.preMic));
    var mic = $('#cb-mic'), cam = $('#cb-cam');
    mic.setAttribute('aria-pressed', String(!v.mic)); cam.setAttribute('aria-pressed', String(!v.camera));
    setText($('#cb-mic-label'), v.mic ? 'Mute' : 'Unmute'); setText($('#cb-cam-label'), v.camera ? 'Stop video' : 'Start video');
    mic.querySelector('use').setAttribute('href', v.mic ? '#i-mic' : '#i-mic-off');
    cam.querySelector('use').setAttribute('href', v.camera ? '#i-camera' : '#i-camera-off');
    setHidden($('#self-off'), v.camera);
    setText($('#ended-sub'), 'You were on a call with ' + withC.name + ' for ' + fmt(v.lastDuration) + '.');
    setText($('#ended-again'), 'Call ' + withC.name + ' again');
  }

  function linkify(text, convId) {
    var n = 0;
    return text.split(/(https?:\/\/[^\s]+)/g).map(function (p, i) {
      if (i % 2 === 0) return esc(p);
      n++;
      return '<a href="#" class="msg-link" data-act="msg.link" data-conv="' + convId + '" data-ground-id="messages.link.' + convId + (n > 1 ? '.' + n : '') + '">' + esc(p) + '</a>';
    }).join('');
  }
  // The bank scam's red-flag phrases get ids so the demo director can read their exact boxes (__stage.scamRects).
  function flagSpans(html, sel, msg) {
    if (sel !== 'scam' || msg.from !== 'them') return html;
    return html
      .replace('URGENT:', '<span id="sn-urgent">URGENT:</span>')
      .replace('within 2 hours', '<span id="sn-2h">within 2 hours</span>')
      .replace(/(<a [^>]*>https?:[^<]*<\/a>)/, '<span id="sn-url">$1</span>');
  }
  function renderMessages() {
    var m = S.msg, q = m.search.trim().toLowerCase();
    var rows = m.order.filter(function (id) {
      var meta = convMeta(id), c = m.convs[id];
      return !q || (meta.name + ' ' + c.msgs.map(function (x) { return x.text; }).join(' ')).toLowerCase().indexOf(q) >= 0;
    }).map(function (id) {
      var meta = convMeta(id), c = m.convs[id], last = c.msgs[c.msgs.length - 1];
      return '<button type="button" class="conv' + (c.unread ? ' unread' : '') + '" data-act="msg.open" data-id="' + id + '" aria-current="' + (m.selected === id) + '" data-ground-id="messages.conv.' + id + '">' +
        '<span class="avatar" style="--c:' + meta.color + '" aria-hidden="true">' + initials(meta.name) + '</span>' +
        '<span class="cv-text"><span class="cv-top"><span class="cv-name">' + esc(meta.name) + '</span><span class="cv-time">' + esc(c.time) + '</span></span>' +
        '<span class="cv-prev">' + (last.from === 'me' ? 'You: ' : '') + esc(last.text) + '</span></span>' + (c.unread ? '<span class="udot" title="Unread"></span>' : '') + '</button>';
    }).join('');
    setHtml($('#conv-list'), rows || '<p class="muted" style="padding:1rem">No messages found.</p>');

    var sel = m.selected, c = sel && m.convs[sel];
    setHidden($('#thread-empty'), !!c); setHidden($('#thread'), !c);
    if (!c) { threadKey = ''; return; }
    var meta = convMeta(sel);
    var av = $('#th-avatar'); setText(av, initials(meta.name)); av.style.setProperty('--c', meta.color);
    setText($('#th-name'), meta.name); setText($('#th-sub'), meta.sub);
    var banner = $('#th-banner');
    setHidden(banner, !(c.blocked || c.reported));
    setText(banner, c.reported ? 'Reported as junk. This number is now blocked.' : 'This number is blocked. You will not get texts from it.');
    var menu = $('#th-menu'); setHidden(menu, !m.menuOpen);
    $('#th-menu-btn').setAttribute('aria-expanded', String(m.menuOpen));
    var html = c.msgs.map(function (x, i) {
      var who = x.from === 'them' && x.who ? '<strong>' + esc(x.who) + ':</strong> ' : '';
      return '<div class="bubble ' + x.from + '" data-kind="block" data-ground-id="messages.msg.' + sel + '.' + i + '"><p>' + who + flagSpans(linkify(x.text, sel), sel, x) + '</p><time>' + esc(x.time) + '</time></div>';
    }).join('');
    var sc = $('#th-scroll'); setHtml(sc, html);
    var key = sel + ':' + c.msgs.length;
    if (key !== threadKey) { threadKey = key; sc.scrollTop = sc.scrollHeight; }
  }

  function renderSettings() {
    var q = S.set.search.trim().toLowerCase(), any = false;
    $$('#set-nav-list .nav-item').forEach(function (b) {
      var show = !q || b.dataset.kw.indexOf(q) >= 0; any = any || show; setHidden(b, !show);
      if (b.dataset.id === S.set.section) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    setHidden($('#set-nores'), any);
    $$('#set-panels .panel').forEach(function (p) { setHidden(p, p.dataset.panel !== S.set.section); });
    var pct = Math.round(SCALES[S.textStep] * 100);
    setText($('#ts-value'), pct + '% · ' + SCALE_NAMES[S.textStep]);
    var sl = $('#ts-slider'); if (sl.value !== String(S.textStep)) sl.value = String(S.textStep);
    $$('input[type="range"]').forEach(function (r) { r.style.setProperty('--f', String((r.value - r.min) / (r.max - r.min))); });
    var br = $('#win-settings [data-input="brightness"]'); if (br && br.value !== String(S.brightness)) br.value = String(S.brightness);
  }

  function renderOverlays() {
    var t = S.toast;
    setHtml($('#toasts'), t ? '<div class="toast" role="status" data-ground-id="desk.toast" data-kind="block" data-desc="Notification banner in the top-right corner of the screen from the Messages app">' +
      '<span class="t-icon">' + icon('chat') + '</span><div class="t-body"><div class="t-app">Messages · now</div><div class="t-title" data-ground-id="desk.toast.title">' + esc(t.title) + '</div>' +
      '<div class="t-text" data-ground-id="desk.toast.text">' + esc(t.text) + '</div>' +
      '<div class="t-actions"><button type="button" class="btn primary" data-act="toast.open" data-ground-id="desk.toast.open">Open</button><button type="button" class="btn" data-act="toast.dismiss" data-ground-id="desk.toast.dismiss">Dismiss</button></div></div></div>' : '');

    var mr = $('#menu-root'), mb = $('[data-ground-id="desk.menu"]');
    mb.setAttribute('aria-expanded', String(S.menu));
    setHtml(mr, S.menu ? '<div class="menu" role="menu">' +
      Object.keys(APPS).map(function (a) { return '<button type="button" role="menuitem" data-act="desk.menu.open" data-app="' + a + '" data-ground-id="desk.menu.' + a + '">' + icon(APPS[a].icon) + APPS[a].name + '</button>'; }).join('') +
      '<hr><button type="button" role="menuitem" data-act="desk.decoy" data-label="Power" data-ground-id="desk.menu.power">' + icon('power') + 'Power options…</button></div>' : '');

    var m = S.modal;
    setHtml($('#modal-root'), m ? '<div class="scrim"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" data-ground-id="modal" data-kind="block"><h2 id="modal-title" data-ground-id="modal.title">' + esc(m.title) + '</h2><p data-ground-id="modal.body">' + esc(m.body) + '</p><div class="m-actions">' +
      m.buttons.map(function (b) { return '<button type="button" class="btn ' + (b.kind || '') + '" data-act="' + b.act + '" data-ground-id="' + b.id + '">' + esc(b.label) + '</button>'; }).join('') + '</div></div></div>' : '');
  }

  /* ------------------------------------------------------------------ geometry / ground truth */
  function clipBox(el) {
    var cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) return null;
    var r = el.getBoundingClientRect();
    var L = r.left, T = r.top, R = r.right, B = r.bottom;
    for (var p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      var pc = getComputedStyle(p);
      if (pc.display === 'none' || parseFloat(pc.opacity) === 0) return null;
      if (pc.overflowX !== 'visible' || pc.overflowY !== 'visible') {
        var pr = p.getBoundingClientRect();
        L = Math.max(L, pr.left); T = Math.max(T, pr.top); R = Math.min(R, pr.right); B = Math.min(B, pr.bottom);
      }
    }
    L = Math.max(L, 0); T = Math.max(T, 0); R = Math.min(R, window.innerWidth); B = Math.min(B, window.innerHeight);
    if (R - L < 1 || B - T < 1) return null;
    return { L: L, T: T, R: R, B: B };
  }
  function unoccluded(el, b) {
    var pts = [[.5, .5], [.2, .5], [.8, .5], [.5, .2], [.5, .8], [.2, .2], [.8, .8]], hits = 0;
    for (var i = 0; i < pts.length; i++) {
      var hit = document.elementFromPoint(b.L + (b.R - b.L) * pts[i][0], b.T + (b.B - b.T) * pts[i][1]);
      if (hit && (el === hit || el.contains(hit))) hits++;
    }
    return hits >= 4;
  }
  function textBox(el, b) {
    var rg = document.createRange(), L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
    rg.selectNodeContents(el);
    Array.prototype.forEach.call(rg.getClientRects(), function (r) {
      if (r.width < 1 || r.height < 1) return;
      L = Math.min(L, r.left); T = Math.min(T, r.top); R = Math.max(R, r.right); B = Math.max(B, r.bottom);
    });
    if (L === Infinity) return b;
    L = Math.max(L, b.L); T = Math.max(T, b.T); R = Math.min(R, b.R); B = Math.min(B, b.B);
    return R - L < 1 || B - T < 1 ? b : { L: L, T: T, R: R, B: B };
  }
  function toNorm(b, space) {
    var W = window.innerWidth, H = window.innerHeight, ox = 0, oy = 0, sw = W, sh = H, z = 1;
    if (space === 'screen') {
      z = 1; sw = screen.width; sh = screen.height;
      ox = window.screenX + Math.max(0, (window.outerWidth - W) / 2);
      oy = window.screenY + Math.max(0, window.outerHeight - H - (window.outerWidth - W) / 2);
      if (document.fullscreenElement || (W === screen.width && H >= screen.height - 1)) { ox = 0; oy = 0; }
    }
    return { xmin: r1((ox + b.L * z) / sw * 1000), ymin: r1((oy + b.T * z) / sh * 1000), xmax: r1((ox + b.R * z) / sw * 1000), ymax: r1((oy + b.B * z) / sh * 1000) };
  }
  function labelOf(el) {
    return (el.getAttribute('aria-label') || (el.tagName === 'INPUT' || el.tagName === 'SELECT' ? el.getAttribute('placeholder') || '' : '') || el.textContent || el.title || '').replace(/\s+/g, ' ').trim().slice(0, 90);
  }
  function kindOf(el) {
    if (el.dataset.kind) return el.dataset.kind;
    var t = el.tagName;
    if (t === 'BUTTON') return el.getAttribute('role') === 'switch' ? 'switch' : el.getAttribute('role') === 'menuitem' ? 'menuitem' : 'button';
    if (t === 'A') return 'link';
    if (t === 'SELECT') return 'select';
    if (t === 'INPUT') return el.type === 'range' ? 'slider' : 'input';
    return 'text';
  }
  function catalog(opts) {
    opts = opts || {};
    var out = [];
    $$('[data-ground-id]').forEach(function (el) {
      var id = el.dataset.groundId, b = clipBox(el), kind = kindOf(el);
      var vis = !!b && (opts.includeOccluded || unoccluded(el, b));
      if (vis && kind === 'text') b = textBox(el, b);
      out.push({ id: id, app: id.split('.')[0], kind: kind, label: labelOf(el), desc: el.dataset.desc || null, visible: vis, box: vis ? toNorm(b, opts.space) : null });
      if (vis && el.type === 'range') {
        var rr = el.getBoundingClientRect(), th = parseFloat(getComputedStyle(document.documentElement).fontSize) * 1.75;
        var frac = (el.value - el.min) / (el.max - el.min), cx = rr.left + th / 2 + (rr.width - th) * frac, cy = rr.top + rr.height / 2;
        out.push({ id: id + '.thumb', app: id.split('.')[0], kind: 'handle', label: labelOf(el) + ' handle', desc: 'Round draggable handle of the slider', visible: true, box: toNorm({ L: cx - th / 2, T: cy - th / 2, R: cx + th / 2, B: cy + th / 2 }, opts.space) });
      }
    });
    return out;
  }
  function rects(opts) {
    var out = {};
    catalog(opts).forEach(function (c) { if (c.visible) out[c.id] = c.box; });
    return out;
  }

  /* ------------------------------------------------------------------ debug overlay */
  var dbgQueued = false;
  function schedDebug() {
    if (!document.getElementById('debug-layer').dataset.on || dbgQueued) return;
    dbgQueued = true;
    requestAnimationFrame(function () { dbgQueued = false; drawDebug(); });
  }
  function drawDebug() {
    var layer = $('#debug-layer'), W = window.innerWidth, H = window.innerHeight, html = '';
    catalog().forEach(function (c) {
      if (!c.visible) return;
      var b = c.box, cont = c.kind === 'container';
      html += '<div class="dbg' + (cont ? ' c' : '') + '" style="left:' + b.xmin / 1000 * W + 'px;top:' + b.ymin / 1000 * H + 'px;width:' + (b.xmax - b.xmin) / 1000 * W + 'px;height:' + (b.ymax - b.ymin) / 1000 * H + 'px"><span>' + esc(c.id) + '</span></div>';
    });
    layer.innerHTML = html;
  }
  window.addEventListener('resize', schedDebug);
  document.addEventListener('scroll', schedDebug, true);

  /* ------------------------------------------------------------------ routing */
  function applyRoute(route) {
    route = String(route || 'desktop').replace(/^#?\/?/, '').replace(/\/+$/, '').toLowerCase() || 'desktop';
    resetState();
    S.route = route;
    var parts = route.split('/'), app = parts[0], sub = parts.slice(1);
    var ok = true;
    if (app === 'desktop') {
      if (sub[0] === 'scam') deliverScam(sub[1]);
      else if (sub[0] === 'genuine') deliverGenuine(parseInt(sub[1], 10) || 0);
      else if (sub[0] === 'menu') S.menu = true;
    } else if (app === 'video') ok = videoRoute(sub);
    else if (app === 'messages') ok = messagesRoute(sub);
    else if (app === 'settings') ok = settingsRoute(sub);
    else ok = false;
    if (!ok) console.warn('[stage] unknown route "' + route + '", showing desktop');
    S.focus = null;
    render();
    return route;
  }
  function videoRoute(sub) {
    openApp('video');
    var s = sub[0] || 'contacts', who = 'lily';
    if (s === 'contacts') return true;
    if (s === 'contact') { if (!contactById(sub[1])) return false; selectContact(sub[1]); return true; }
    if (s === 'settings') { S.video.view = 'settings'; return true; }
    if (['lily', 'precall', 'calling', 'call-screen', 'call', 'ended'].indexOf(s) < 0) return false;
    selectContact(who);
    if (s === 'lily') return true;
    startPrecall(true);
    if (s === 'precall') { if (sub[1] === 'camera-off') S.video.preCamera = false; return true; }
    startCall();
    if (s === 'calling') { clearTimeout(ringT); return true; }
    connectCall(); clearTimeout(ringT);
    if (s === 'ended') { S.video.seconds = 42; endCall(); return true; }
    if (sub[1] === 'muted') S.video.mic = false;
    if (sub[1] === 'camera-off') S.video.camera = false;
    return true;
  }
  function messagesRoute(sub) {
    var s = sub[0] || 'inbox', x = sub[1];
    var bases = { scam: 'scam', 'scam-parcel': 'scam_parcel', 'scam-family': 'scam_family' };
    if (s === 'inbox') { openApp('messages'); return true; }
    if (s === 'scam-list') { deliverScam(); openApp('messages'); return true; }
    if (bases[s]) {
      var key = deliverScam(s === 'scam' ? 0 : s);
      openApp('messages'); openConv(key);
      if (x === 'menu') S.msg.menuOpen = true;
      else if (x === 'reported') { var c = S.msg.convs[key]; c.reported = true; c.blocked = true; }
      else if (x === 'blocked') S.msg.convs[key].blocked = true;
      else if (x === 'link') ACT['msg.link']({ dataset: { conv: key } }, { preventDefault: function () {} });
      else if (x) return false;
      return true;
    }
    if (s === 'genuine') {
      var gk = deliverGenuine(parseInt(x, 10) || 0);
      openApp('messages'); openConv(gk); return true;
    }
    return false;
  }
  function settingsRoute(sub) {
    openApp('settings');
    var s = sub[0] || 'general';
    if (!PANELS.some(function (p) { return p.id === s; })) return false;
    S.set.section = s;
    if (s === 'display' && sub[1] === 'size') setTextStep(parseInt(sub[2], 10) || 0, 'fixture');
    else if (s === 'display' && sub[1] === 'bigger') setTextStep(1, 'fixture');
    else if (s === 'advanced' && sub[1] === 'reset-confirm') ACT['set.reset']();
    else if (sub[1]) return false;
    return true;
  }

  /* ------------------------------------------------------------------ public API */
  var api = {
    version: '1.0.0',
    ready: false,
    flows: FLOWS,
    rects: function (opts) { return rects(opts); },
    rectOf: function (id, opts) { var r = rects(opts)[id]; return r || null; },
    catalog: function (opts) { return catalog(opts); },
    // Interactive demo: exact per-line boxes of the bank scam's red-flag phrases, only while that thread is on screen
    // (empty otherwise). Deliberately not part of rects()/catalog().
    scamRects: function (opts) {
      var out = {};
      if (S.app !== 'messages' || S.msg.selected !== 'scam') return out;
      var space = opts && opts.space;
      var lines = function (rects) {
        var list = [];
        Array.prototype.forEach.call(rects, function (r) { if (r.width > 1 && r.height > 1) list.push(toNorm({ L: r.left, T: r.top, R: r.right, B: r.bottom }, space)); });
        return list;
      };
      var map = { urgent: 'sn-urgent', twoHours: 'sn-2h', url: 'sn-url' };
      Object.keys(map).forEach(function (k) {
        var el = document.getElementById(map[k]);
        var l = el ? lines(el.getClientRects()) : [];
        if (l.length) out[k] = l;
      });
      var sub = document.getElementById('th-sub');
      if (sub && sub.textContent.indexOf('7700 900482') >= 0) {
        var rg = document.createRange(); rg.selectNodeContents(sub);
        var pl = lines(rg.getClientRects());
        if (pl.length) out.phone = pl;
      }
      return out;
    },
    // Opens a Messages conversation without resetting anything else (the director's scam beat); false when it does not exist.
    openThread: function (id) { if (!S.msg.convs[id]) return false; openApp('messages'); openConv(id); render(); return true; },
    closeApp: function (app) { closeApp(app); render(); return true; },
    ids: function () { return $$('[data-ground-id]').map(function (e) { return e.dataset.groundId; }); },
    duplicateIds: function () { var seen = {}, dup = []; api.ids().forEach(function (i) { if (seen[i] && dup.indexOf(i) < 0) dup.push(i); seen[i] = 1; }); return dup; },
    state: function () {
      var v = S.video, m = S.msg;
      return JSON.parse(JSON.stringify({
        route: S.route, app: S.app, running: S.running, still: STILL,
        viewport: { width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio },
        textStep: S.textStep, textScalePct: Math.round(SCALES[S.textStep] * 100), rootFontPx: parseFloat(getComputedStyle(document.documentElement).fontSize),
        theme: S.toggles['settings.display.dark_theme'] ? 'dark' : 'light', highContrast: !!S.toggles['settings.display.high_contrast'], brightness: S.brightness,
        video: { view: v.view, selected: v.selected, withContact: v.withContact, callState: v.callState, seconds: v.seconds, mic: v.mic, camera: v.camera, preMic: v.preMic, preCamera: v.preCamera, callsStarted: v.callsStarted, lastDuration: v.lastDuration },
        messages: {
          selected: m.selected, order: m.order, unread: m.order.filter(function (id) { return m.convs[id].unread; }), delivered: m.delivered, linkClicked: m.linkClicked, deleted: m.deleted,
          reported: m.order.filter(function (id) { return m.convs[id].reported; }), blocked: m.order.filter(function (id) { return m.convs[id].blocked; }), menuOpen: m.menuOpen, lastSent: m.lastSent
        },
        settings: { section: S.set.section },
        toast: S.toast ? { conv: S.toast.conv, title: S.toast.title } : null, modal: S.modal ? { title: S.modal.title } : null, desktopMenuOpen: S.menu,
        eventCount: events.length
      }));
    },
    events: function () { return events.slice(); },
    lastEvent: function (type) { for (var i = events.length - 1; i >= 0; i--) if (!type || events[i].type === type) return events[i]; return null; },
    clearEvents: function () { events = []; },
    onEvent: function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; },
    reset: function () { applyRoute('desktop'); events = []; return api.state(); },
    go: function (route) { applyRoute(route); return api.state(); },
    setStep: function (flowId, n) {
      var f = FLOWS[flowId]; if (!f) throw new Error('unknown flow ' + flowId);
      var route = n <= 0 ? f.start : (f.steps[Math.min(n, f.steps.length) - 1] || {}).after;
      applyRoute(route); return api.state();
    },
    deliverScam: function (variant) { var k = deliverScam(variant); return { conv: k }; },
    deliverGenuine: function (i) { var k = deliverGenuine(i); return { conv: k }; },
    connectCall: function () { connectCall(); render(); return api.state(); },
    setTextStep: function (n) { setTextStep(n, 'api'); render(); return api.state(); },
    debug: function (on) {
      var layer = $('#debug-layer');
      if (on) { layer.dataset.on = '1'; drawDebug(); } else { delete layer.dataset.on; layer.innerHTML = ''; }
      return !!on;
    },
    hotkeys: { S: 'deliver scam text', G: 'deliver next genuine text', 'Shift+R': 'reset', D: 'toggle rect debug overlay', F: 'toggle fullscreen', Esc: 'close pop-up' }
  };
  window.__stage = api;

  /* ------------------------------------------------------------------ init */
  build();
  resetState();
  window.addEventListener('hashchange', function () { applyRoute(location.hash); });
  var first = Q.get('fixture') || location.hash.replace(/^#\/?/, '') || 'desktop';
  applyRoute(first);
  events = [];
  if (!STILL) clockT = setInterval(function () { updateClock(); }, 15000);
  if (STILL) document.documentElement.classList.add('still');
  if (DEBUG) api.debug(true);
  api.ready = true;
  try { window.dispatchEvent(new Event('stage:ready')); } catch (e) { /* ignore */ }
})();

// Exit button (interactive demo only): click once to arm, click again within 3 s to close the practice desktop.
(function () {
  var btn = document.getElementById('exit-demo');
  if (!btn || new URLSearchParams(location.search).get('exit') !== '1') return;
  btn.hidden = false;
  var timer = null;
  function disarm() { btn.classList.remove('armed'); btn.textContent = 'Exit demo'; timer = null; }
  btn.addEventListener('click', function () {
    if (!timer) {
      btn.classList.add('armed');
      btn.textContent = 'Click again to exit';
      timer = setTimeout(disarm, 3000);
      return;
    }
    clearTimeout(timer);
    btn.textContent = 'Closing\u2026';
    window.close();
    setTimeout(function () { btn.textContent = 'You can close this tab now'; }, 600);
  });
})();
