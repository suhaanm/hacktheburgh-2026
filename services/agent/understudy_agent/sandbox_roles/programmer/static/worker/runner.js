/* The only place participant code runs: a dedicated Web Worker. Served by /worker/runner.js with its own CSP (connect-src 'none', unsafe-eval
   allowed for this worker only), so the page itself keeps a CSP without eval. Network APIs are removed before any user code is evaluated. */
'use strict';
const post = self.postMessage.bind(self);
for (const k of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'importScripts', 'indexedDB', 'caches', 'BroadcastChannel', 'Worker', 'SharedWorker', 'postMessage']) {
  try { Object.defineProperty(self, k, { value: undefined, configurable: false, writable: false }); } catch (e) { try { self[k] = undefined; } catch (e2) { /* keep going */ } }
}
function show(v) {
  if (v === undefined) return 'undefined';
  if (typeof v === 'number' && Number.isNaN(v)) return 'NaN';
  if (typeof v === 'function') return '[function]';
  try {
    return JSON.stringify(v, (k, x) => (x === undefined ? '__undefined__' : (typeof x === 'number' && Number.isNaN(x) ? '__nan__' : x)))
      .replace(/"__undefined__"/g, 'undefined').replace(/"__nan__"/g, 'NaN');
  } catch (e) { return String(v); }
}
function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== typeof b || a === null || b === null || typeof a !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && deepEqual(a[k], b[k]));
}
function assertEqual(actual, expected) { if (!deepEqual(actual, expected)) throw new Error('expected ' + show(expected) + ' but got ' + show(actual)); }
function assertThrows(fn) { try { fn(); } catch (e) { return; } throw new Error('expected an error to be thrown'); }
onmessage = (e) => {
  const m = e.data;
  const out = { mode: m.mode };
  try {
    if (m.mode === 'eval') {
      const f = new Function(m.source + '\n;return (' + m.expr + ');');
      out.value = show(f());
    } else {
      const tests = [];
      const test = (name, fn) => tests.push({ name, fn });
      let code = m.source + '\n;' + m.testCode;
      for (const h of (m.hidden || [])) code += '\ntest(' + JSON.stringify(h.name) + ', () => { ' + h.code + ' });';
      new Function('test', 'assertEqual', 'assertThrows', code)(test, assertEqual, assertThrows);
      out.results = tests.map((t) => {
        try { t.fn(); return { name: t.name, ok: true }; }
        catch (err) { return { name: t.name, ok: false, error: String((err && err.message) || err).slice(0, 300), type: String((err && err.name) || 'Error') }; }
      });
    }
  } catch (err) { out.error = (err && err.name ? err.name + ': ' : '') + String((err && err.message) || err).slice(0, 300); }
  post(out);
};
