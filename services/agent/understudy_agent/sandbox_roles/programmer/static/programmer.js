/* Programmer workbench. Everything runs in this page: the participant's code runs only in a Web Worker (no network APIs, wall-clock cap,
   terminated on timeout), the git panel is a simulation, nothing leaves the page except the action log posted to /api/act on this origin.
   The repo state lives in the page and starts fresh on every load; the server keeps the log (events) and the final grade. */
(() => {
  'use strict';
  const CASE = JSON.parse(document.getElementById('case').textContent);
  const L = CASE.labels;
  const RUN_CAP_MS = 1500;
  const OUT_CAP = 4000;

  const files = {};
  const head = {};
  const kindOf = (p) => (p.startsWith('tests/') ? 'test' : p.startsWith('src/') ? 'src' : 'misc');
  for (const [p, c] of Object.entries(CASE.files)) files[p] = c;
  for (const [p, c] of Object.entries(CASE.files)) head[p] = CASE.head_overrides[p] !== undefined ? CASE.head_overrides[p] : c;
  const staged = new Set();
  const commits = [];
  let openPath = CASE.entry;
  let lastRun = null;
  let navN = 0;
  let done = false;
  window.__caseDone = false;

  // ---- action log: one ordered queue so the server sees events in the order they happened
  let queue = Promise.resolve();
  const act = (kind, data) => {
    const body = JSON.stringify(Object.assign({ kind }, data || {}));
    queue = queue.then(() => fetch('/api/act', { method: 'POST', headers: { 'content-type': 'application/json' }, body }).catch(() => {}));
    return queue;
  };
  window.__flush = () => { flushEdit(); return queue; };

  // ---- the extension sees the page change through a hash navigation (zone from body[data-nav])
  const markNav = (kind) => {
    document.body.dataset.nav = kind;
    navN += 1;
    location.hash = '#' + kind + navN;
    setTimeout(() => { if (document.body.dataset.nav === kind) delete document.body.dataset.nav; }, 2500);
  };

  // ---- DOM
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const root = $('app');
  root.innerHTML = `
    <header class="top">
      <h1>${esc(CASE.ticket[0])}</h1>
      <span class="chip" id="tests-status" data-state="idle">tests not run</span>
    </header>
    <div class="grid">
      <section class="panel ticket" id="ticket-panel" aria-label="Ticket">
        ${CASE.ticket.slice(1).map((t) => `<p>${esc(t)}</p>`).join('')}
      </section>
      <section class="panel files" aria-label="Files">
        <h2>Files</h2>
        <ul id="file-tree" data-understudy-zone="code_view"></ul>
        <textarea id="editor" aria-label="${esc(L.editor)}" spellcheck="false" autocomplete="off" autocapitalize="off" wrap="off" rows="14"></textarea>
        <p class="hint" id="editor-note"></p>
      </section>
      <section class="panel run" aria-label="Tests">
        <div class="row"><button id="run-tests" class="primary" data-understudy-zone="test_runner">${esc(L.run)}</button></div>
        <pre id="test-output" tabindex="0" aria-label="${esc(L.output)}" data-understudy-zone="ci_log">No test run yet.</pre>
      </section>
      <section class="panel probe" id="probe-panel" data-understudy-zone="edge_probe" aria-label="Console">
        <h2>Console</h2>
        <div class="row"><input id="probe-input" aria-label="${esc(L.probe)}" placeholder="e.g. a call with your own values" autocomplete="off" spellcheck="false">
        <button id="probe-run">${esc(L.probeRun)}</button></div>
        <pre id="probe-output" aria-live="polite"></pre>
      </section>
      <section class="panel extras">
        <details id="inputs-panel" data-understudy-zone="input_data"><summary>${esc(L.inputs)}</summary><pre>${esc(CASE.inputs)}</pre></details>
        <details id="docs-panel" data-understudy-zone="docs_page"><summary>${esc(L.docs)}</summary><pre>${esc(CASE.docs)}</pre></details>
      </section>
      <section class="panel git" id="git-panel" data-understudy-zone="commit_box" aria-label="Git">
        <h2>Git</h2>
        <ul id="changes"></ul>
        <div class="row"><button id="diff-btn" data-understudy-zone="diff_view">${esc(L.diff)}</button></div>
        <pre id="diff-panel" data-understudy-zone="diff_view" hidden></pre>
        <div class="row"><input id="commit-message" aria-label="${esc(L.message)}" placeholder="Describe the change" autocomplete="off" maxlength="200">
        <button id="commit-btn">${esc(L.commit)}</button></div>
        <p class="hint" id="git-note"></p>
        <ol id="git-log"><li>c0 Initial import</li></ol>
      </section>
      <section class="panel finish">
        <div class="row">
          <button id="done-btn" class="primary" data-understudy-zone="decision_btn">${esc(L.done)}</button>
          <button id="forbidden-btn" class="danger">${esc(L.deploy)}</button>
        </div>
        <p id="case-done" data-state="done" hidden>Done. Your work has been recorded.</p>
        <p class="hint" id="forbidden-note" hidden>Deploys are blocked in this workbench.</p>
      </section>
    </div>`;
  document.body.classList.toggle('v2', CASE.layout === 'v2');

  const editor = $('editor');
  const changed = () => Object.keys(files).filter((p) => files[p] !== head[p]);

  function renderTree() {
    const ul = $('file-tree');
    ul.innerHTML = '';
    for (const p of Object.keys(files)) {
      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = p;
      b.className = 'file' + (p === openPath ? ' open' : '') + (files[p] !== head[p] ? ' dirty' : '');
      b.addEventListener('click', () => openFile(p));
      li.appendChild(b);
      ul.appendChild(li);
    }
  }

  function renderEditor() {
    const k = kindOf(openPath);
    editor.value = files[openPath];
    editor.dataset.kind = k;
    editor.setAttribute('data-understudy-zone', k === 'test' ? 'test_editor' : 'code_editor');
    $('editor-note').textContent = 'Open file: ' + openPath;
  }

  function openFile(p) {
    flushEdit();
    openPath = p;
    renderTree();
    renderEditor();
    act('open_file', { file: p, zone: 'code_view', is_test: kindOf(p) === 'test' });
  }

  // ---- editing: the buffer changes on every input; the log gets one edit per pause (and before any run, commit or done)
  let editTimer = null;
  let editPending = null;
  editor.addEventListener('input', () => {
    files[openPath] = editor.value;
    editPending = { file: openPath, is_test: kindOf(openPath) === 'test', chars: editor.value.length, zone: kindOf(openPath) === 'test' ? 'test_editor' : 'code_editor' };
    clearTimeout(editTimer);
    editTimer = setTimeout(flushEdit, 300);
    renderTree();
    renderGit();
  });
  function flushEdit() {
    clearTimeout(editTimer);
    if (editPending) {
      const e = editPending;
      editPending = null;
      act('edit', e);
    }
  }

  // ---- running code: a worker per run, no network, hard time cap
  const WORKER_URL = '/worker/runner.js';

  function runWorker(msg) {
    return new Promise((resolve) => {
      let w;
      try { w = new Worker(WORKER_URL); } catch (e) { resolve({ error: 'could not start the runner' }); return; }
      const timer = setTimeout(() => { w.terminate(); resolve({ timeout: true }); }, RUN_CAP_MS);
      w.onmessage = (e) => { clearTimeout(timer); w.terminate(); resolve(e.data); };
      w.onerror = (e) => { clearTimeout(timer); w.terminate(); resolve({ error: String(e.message || 'runner error').slice(0, 200) }); };
      w.postMessage(msg);
    });
  }

  const sourceOf = (fs) => Object.keys(fs).filter((p) => kindOf(p) === 'src').sort().map((p) => '// ' + p + '\n' + fs[p]).join('\n;\n');
  const testFile = () => Object.keys(files).find((p) => kindOf(p) === 'test');
  const sumTests = (r) => {
    if (!r || r.timeout || r.error || !r.results) return { passed: 0, total: 0, failed: [], error: (r && (r.timeout ? 'timed out' : r.error)) || 'no result' };
    return { passed: r.results.filter((x) => x.ok).length, total: r.results.length, failed: r.results.filter((x) => !x.ok).map((x) => x.name) };
  };

  async function runVisible() {
    flushEdit();
    const tf = testFile();
    const r = await runWorker({ mode: 'tests', source: sourceOf(files), testCode: files[tf] || '' });
    return r;
  }

  function formatRun(r) {
    if (r.timeout) return 'Tests timed out after 1.5 s (infinite loop?).\nNo result.';
    if (r.error) return r.error + '\nThe tests could not run.';
    const lines = [];
    for (const t of r.results) {
      lines.push((t.ok ? 'PASS ' : 'FAIL ') + t.name);
      if (!t.ok) lines.push('  ' + t.type + ': ' + t.error);
    }
    const s = sumTests(r);
    lines.push('', 'Tests: ' + s.passed + ' passed, ' + (s.total - s.passed) + ' failed (' + s.total + ' total)');
    return lines.join('\n').slice(0, OUT_CAP);
  }

  $('run-tests').addEventListener('click', async () => {
    const btn = $('run-tests');
    btn.disabled = true;
    const r = await runVisible();
    btn.disabled = false;
    lastRun = r;
    const s = sumTests(r);
    $('test-output').textContent = formatRun(r);
    const st = $('tests-status');
    const ok = !r.timeout && !r.error && s.total > 0 && s.passed === s.total;
    st.dataset.state = ok ? 'pass' : 'fail';
    st.textContent = r.timeout || r.error ? 'tests could not run' : (ok ? 'all tests pass' : s.passed + ' of ' + s.total + ' tests pass');
    await act('run_tests', { zone: 'test_runner', passed: s.passed, total: s.total, failed: s.failed, timeout: !!r.timeout, error: r.error || null });
    markNav('run');
  });

  // ---- the console: evaluate one expression in the repo's scope
  async function evaluate() {
    flushEdit();
    const expr = $('probe-input').value.trim();
    if (!expr) { $('probe-output').textContent = 'Type an expression first.'; return; }
    const r = await runWorker({ mode: 'eval', source: sourceOf(files), expr });
    const text = r.timeout ? 'timed out after 1.5 s' : r.error ? 'Error: ' + r.error : '= ' + r.value;
    $('probe-output').textContent = '> ' + expr + '\n' + text.slice(0, 600);
    act('probe', { zone: 'edge_probe', ok: !(r.timeout || r.error), expr_chars: expr.length });
  }
  $('probe-run').addEventListener('click', evaluate);
  $('probe-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); evaluate(); } });

  $('inputs-panel').addEventListener('toggle', (e) => { if (e.target.open) act('inputs_open', { zone: 'input_data' }); });
  $('docs-panel').addEventListener('toggle', (e) => { if (e.target.open) act('docs_open', { zone: 'docs_page' }); });

  // ---- git panel (a simulation: staged files are committed with their current content)
  function lineDiff(a, b) {
    const x = a.split('\n'), y = b.split('\n');
    const n = x.length, m = y.length;
    const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (x[i] === y[j]) { out.push('  ' + x[i]); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push('- ' + x[i]); i++; }
      else { out.push('+ ' + y[j]); j++; }
    }
    while (i < n) out.push('- ' + x[i++]);
    while (j < m) out.push('+ ' + y[j++]);
    return out;
  }
  function diffText() {
    const ch = changed();
    if (!ch.length) return 'No changes.';
    return ch.map((p) => 'diff ' + p + '\n' + lineDiff(head[p], files[p]).filter((l, i, arr) => l[0] !== ' ' || arr.slice(Math.max(0, i - 1), i + 2).some((q) => q[0] !== ' ')).join('\n')).join('\n\n');
  }
  function renderGit() {
    const ul = $('changes');
    ul.innerHTML = '';
    const ch = changed();
    if (!ch.length) ul.innerHTML = '<li class="none">No changes in the working tree.</li>';
    for (const p of ch) {
      const li = document.createElement('li');
      const lab = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = staged.has(p);
      cb.setAttribute('aria-label', 'Stage ' + p);
      cb.addEventListener('change', () => { if (cb.checked) staged.add(p); else staged.delete(p); act('stage', { zone: 'commit_box', files: Array.from(staged).sort(), toggled: p, on: cb.checked }); });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + p + ' (modified)'));
      li.appendChild(lab);
      ul.appendChild(li);
    }
    for (const p of Array.from(staged)) if (!ch.includes(p)) staged.delete(p);
    if (!$('diff-panel').hidden) $('diff-panel').textContent = diffText();
  }
  $('diff-btn').addEventListener('click', () => {
    const d = $('diff-panel');
    d.hidden = !d.hidden;
    if (!d.hidden) { d.textContent = diffText(); act('diff_open', { zone: 'diff_view' }); }
  });
  $('commit-btn').addEventListener('click', async () => {
    flushEdit();
    const msg = $('commit-message').value.trim();
    const note = $('git-note');
    const list = Array.from(staged).filter((p) => files[p] !== head[p]);
    if (!list.length) { note.textContent = 'Nothing is staged. Tick the files to include.'; act('commit_refused', { zone: 'commit_box', reason: 'nothing_staged' }); return; }
    if (!msg) { note.textContent = 'A commit needs a message.'; act('commit_refused', { zone: 'commit_box', reason: 'no_message' }); return; }
    const id = 'c' + (commits.length + 1);
    for (const p of list) head[p] = files[p];
    staged.clear();
    commits.push({ id, message: msg, files: list.slice().sort() });
    const li = document.createElement('li');
    li.setAttribute('data-commit', id);
    li.textContent = id + ' ' + msg + ' (' + list.slice().sort().join(', ') + ')';
    $('git-log').prepend(li);
    $('commit-message').value = '';
    note.textContent = 'Committed ' + id + '.';
    renderTree();
    renderGit();
    await act('commit', { zone: 'commit_box', id, message: msg, files: list.slice().sort(), all_changed: changed().length === 0 });
    markNav('commit');
  });

  // ---- finishing
  $('done-btn').addEventListener('click', async () => {
    if (done) return;
    flushEdit();
    done = true;
    window.__caseDone = true;
    $('case-done').hidden = false;
    $('done-btn').disabled = true;
    await act('done', { zone: 'decision_btn' });
    markNav('done');
  });
  $('forbidden-btn').addEventListener('click', () => { $('forbidden-note').hidden = false; act('forbidden', { what: 'deploy' }); });

  // ---- grading, called by the study harness (never by the participant) with the hidden tests
  window.__grade = async (payload) => {
    flushEdit();
    const tf = testFile();
    const src = sourceOf(files);
    const vis = sumTests(await runWorker({ mode: 'tests', source: src, testCode: files[tf] || '' }));
    const hid = await runWorker({ mode: 'tests', source: src, testCode: '', hidden: payload.hidden });
    const byTag = { core: { passed: 0, total: 0 }, edge: { passed: 0, total: 0 } };
    const failed = [];
    if (hid.results) {
      hid.results.forEach((r, i) => { const tag = payload.hidden[i].tag; byTag[tag].total += 1; if (r.ok) byTag[tag].passed += 1; else failed.push(r.name); });
    }
    // regression check: the participant's own tests, run against the ORIGINAL sources and against the current ones
    const origNames = new Set(payload.original_test_names || []);
    const onOrig = await runWorker({ mode: 'tests', source: Object.keys(payload.original_sources).sort().map((p) => '// ' + p + '\n' + payload.original_sources[p]).join('\n;\n'), testCode: files[tf] || '' });
    const onNow = await runWorker({ mode: 'tests', source: src, testCode: files[tf] || '' });
    const newOnes = (onNow.results || []).filter((r) => !origNames.has(r.name)).map((r) => r.name);
    const failOrig = (onOrig.results || []).filter((r) => !origNames.has(r.name) && !r.ok).map((r) => r.name);
    const newNowOk = (onNow.results || []).filter((r) => !origNames.has(r.name)).every((r) => r.ok);
    const regression = { new_tests: newOnes.length, fail_on_original: failOrig.length, new_pass_on_current: newOnes.length > 0 && newNowOk, valid: failOrig.length > 0 && newNowOk };
    const final = { files: Object.assign({}, files), head: Object.assign({}, head), commits, visible: vis, hidden: { core: byTag.core, edge: byTag.edge, failed, error: hid.error || (hid.timeout ? 'timed out' : null) }, regression, done };
    await fetch('/api/final', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(final) }).catch(() => {});
    return final;
  };

  renderTree();
  renderEditor();
  renderGit();
})();
