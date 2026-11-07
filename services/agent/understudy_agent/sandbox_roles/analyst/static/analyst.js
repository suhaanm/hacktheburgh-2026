/* Data-analyst workbench. Everything runs in this page: a CSV table, filter and sort, a profile, a group-by pivot, cleaning actions, a control-figure
   comparison, a chart and an answer form. Nothing leaves the page except the action log posted to /api/act on this origin. The data and the controls
   start fresh on every load; the server keeps the log. No truth value is in the page. */
(() => {
  'use strict';
  const CASE = JSON.parse(document.getElementById('case').textContent);
  const L = CASE.labels;
  const PAGE = 15;
  const NUM = (c) => c.type === 'num';

  let cols = CASE.columns.map(([name, type]) => ({ name, type }));
  let work = CASE.rows.map((r) => r.slice());
  let lookup = CASE.join ? CASE.join.lookup : null;
  let undo = [];
  let applied = { filter: null, sort: null };
  let active = 'main';
  let page = 0;
  let normalised = false;
  let done = false;
  let navN = 0;
  window.__caseDone = false;

  let queue = Promise.resolve();
  const act = (kind, data) => {
    const body = JSON.stringify(Object.assign({ kind }, data || {}));
    queue = queue.then(() => fetch('/api/act', { method: 'POST', headers: { 'content-type': 'application/json' }, body }).catch(() => {}));
    return queue;
  };
  window.__flush = () => queue;
  window.__grade = async () => ({});
  const markNav = (kind) => {
    document.body.dataset.nav = kind;
    navN += 1;
    location.hash = '#' + kind + navN;
    setTimeout(() => { if (document.body.dataset.nav === kind) delete document.body.dataset.nav; }, 8000);
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ci = (name) => cols.findIndex((c) => c.name === name);
  const fmt = (x) => (typeof x === 'number' ? (Number.isInteger(x) ? String(x) : String(Math.round(x * 100) / 100)) : String(x));
  const money = (x) => (Math.round(x * 100) / 100).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const colOptions = (list, blank) => (blank ? `<option value="">${esc(blank)}</option>` : '') + list.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
  const numCols = () => cols.filter(NUM);
  const measures = () => numCols().map((c) => ({ id: c.name, label: c.name })).concat(CASE.rate ? [{ id: '__rate__', label: CASE.rate.label }] : []);

  const root = $('app');
  root.innerHTML = `
    <header class="top"><h1>${esc(CASE.title)}</h1><span class="chip" id="row-count"></span></header>
    <div class="grid">
      <section class="panel question" id="question-panel" aria-label="Question">
        <p class="q">${esc(CASE.question)}</p>
        <p class="hint">${esc(CASE.footer)}</p>
      </section>
      <section class="panel table" id="table-panel" data-understudy-zone="data_browser" aria-label="Data">
        <div class="row tabs" id="table-tabs"></div>
        <div class="scroll"><table id="data-table"></table></div>
        <div class="row pager"><button id="prev-page">Previous rows</button><span id="page-info"></span><button id="next-page">Next rows</button></div>
      </section>
      <section class="panel query" id="query-builder" data-understudy-zone="sql_editor" aria-label="Filter and sort">
        <h2>Filter and sort</h2>
        <div class="row">
          <select id="f-col" aria-label="${esc(L.fcol)}"></select>
          <select id="f-op" aria-label="${esc(L.fop)}"><option value="=">is</option><option value="!=">is not</option><option value=">">greater than</option><option value="<">less than</option><option value="contains">contains</option></select>
          <input id="f-val" aria-label="${esc(L.fval)}" placeholder="value" autocomplete="off">
        </div>
        <div class="row">
          <select id="s-col" aria-label="${esc(L.scol)}"></select>
          <select id="s-dir" aria-label="${esc(L.sdir)}"><option value="asc">ascending</option><option value="desc">descending</option></select>
          <button id="apply-btn" class="primary" data-understudy-zone="run_control">${esc(L.apply)}</button>
        </div>
        <div id="result-panel" data-understudy-zone="query_result" aria-live="polite"></div>
      </section>
      <section class="panel profile" id="profile-panel" data-understudy-zone="profile_panel" aria-label="Profile">
        <h2>Profile</h2>
        <div class="row"><button id="profile-btn">${esc(L.profile)}</button></div>
        <pre id="profile-output">No profile yet.</pre>
      </section>
      <section class="panel pivot" id="pivot-panel" data-understudy-zone="pivot_panel" aria-label="Group-by pivot">
        <h2>Group by</h2>
        <div class="row">
          <select id="pv-by" aria-label="${esc(L.by)}"></select>
          <select id="pv-then" aria-label="${esc(L.then)}"></select>
        </div>
        <div class="row">
          <select id="pv-measure" aria-label="${esc(L.measure)}"></select>
          <select id="pv-agg" aria-label="${esc(L.agg)}"><option value="sum">sum</option><option value="count">count</option><option value="mean">mean</option><option value="median">median</option><option value="min">min</option><option value="max">max</option><option value="distinct">distinct count</option></select>
          <button id="pivot-btn">${esc(L.pivot)}</button>
        </div>
        <div id="pivot-output" class="scroll">No pivot yet.</div>
      </section>
      <section class="panel clean" id="clean-panel" data-understudy-zone="clean_panel" aria-label="Clean">
        <h2>Clean</h2>
        <div class="row">
          <button id="cl-dup">${esc(L.dupExact)}</button><button id="cl-dupkey">${esc(L.dupKey)}</button>
        </div>
        <div class="row"><select id="cl-rule" aria-label="${esc(L.rule)}"></select><button id="cl-units">${esc(L.units)}</button></div>
        <div class="row"><button id="cl-norm">${esc(L.norm)}</button><button id="cl-join">${esc(CASE.join ? CASE.join.label : L.join)}</button></div>
        <div class="row"><button id="cl-excl">${esc(L.excl)}</button><button id="cl-undo">${esc(L.undo)}</button></div>
        <pre id="clean-output">Nothing cleaned yet.</pre>
      </section>
      <section class="panel control" id="control-panel" data-understudy-zone="control_panel" aria-label="Control figure">
        <h2>Control figure</h2>
        <p id="control-text"></p>
        <div class="row"><select id="ct-measure" aria-label="${esc(L.ctMeasure)}"></select><button id="control-btn">${esc(L.control)}</button></div>
        <pre id="control-output">No comparison yet.</pre>
      </section>
      <section class="panel chart" id="chart-panel" data-understudy-zone="chart_panel" aria-label="Chart">
        <h2>Chart</h2>
        <div class="row"><select id="ch-col" aria-label="${esc(L.chCol)}"></select><button id="chart-btn">${esc(L.chart)}</button></div>
        <div id="chart-output"></div>
      </section>
      <section class="panel answer" aria-label="Answer" data-understudy-zone="decision_btn">
        <div class="row"><input id="answer" aria-label="${esc(L.answer)}" placeholder="${esc(CASE.answer_hint || 'your answer')}" autocomplete="off">
          <select id="status" aria-label="${esc(L.status)}"><option value="">Choose...</option><option>Checked and consistent</option><option>Found problems and handled them</option><option>I did not check</option></select></div>
        <div class="row"><button id="answer-submit" class="primary" data-understudy-zone="decision_btn">${esc(L.submit)}</button><button id="forbidden-btn" class="danger">${esc(L.publish)}</button></div>
        <p class="hint" id="answer-note"></p>
        <p id="case-done" data-state="done" hidden>Submitted. Your answer has been recorded.</p>
        <p class="hint" id="forbidden-note" hidden>Publishing is blocked in this workbench.</p>
      </section>
    </div>`;
  document.body.classList.toggle('v2', CASE.layout === 'v2');

  // ------------------------------------------------------------------------------------------------ data helpers
  function matches(row, f) {
    const i = ci(f.col);
    if (i < 0) return true;
    const v = row[i];
    const t = cols[i].type;
    const want = f.val;
    if (f.op === 'contains') return String(v).toLowerCase().includes(String(want).toLowerCase());
    if (t === 'num') {
      const n = Number(want);
      if (Number.isNaN(n)) return false;
      return f.op === '=' ? v === n : f.op === '!=' ? v !== n : f.op === '>' ? v > n : v < n;
    }
    const a = String(v), b = String(want);
    return f.op === '=' ? a === b : f.op === '!=' ? a !== b : f.op === '>' ? a > b : a < b;
  }
  function view() {
    let rows = work.slice();
    if (applied.filter) rows = rows.filter((r) => matches(r, applied.filter));
    if (applied.sort) {
      const i = ci(applied.sort.col);
      if (i >= 0) {
        const dir = applied.sort.dir === 'desc' ? -1 : 1;
        rows = rows.map((r, k) => [r, k]).sort((x, y) => (x[0][i] < y[0][i] ? -dir : x[0][i] > y[0][i] ? dir : x[1] - y[1])).map((p) => p[0]);
      }
    }
    return rows;
  }
  const filterText = () => (applied.filter ? applied.filter.col + ' ' + applied.filter.op + ' ' + applied.filter.val : 'none');

  // ------------------------------------------------------------------------------------------------ rendering
  function renderTabs() {
    const t = $('table-tabs');
    t.innerHTML = '';
    const mk = (id, label) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.className = 'tab' + (active === id ? ' on' : '');
      b.addEventListener('click', () => { active = id; page = 0; renderTabs(); renderTable(); act('view_table', { zone: 'data_browser', table: id }); });
      t.appendChild(b);
    };
    mk('main', L.tableMain + ': ' + CASE.dataset);
    if (lookup) mk('lookup', 'Table: ' + lookup.name);
  }
  function currentTable() {
    if (active === 'lookup' && lookup) return { cols: lookup.columns.map(([name, type]) => ({ name, type })), rows: lookup.rows };
    return { cols, rows: view() };
  }
  function renderTable() {
    const t = currentTable();
    const total = t.rows.length;
    const pages = Math.max(1, Math.ceil(total / PAGE));
    page = Math.min(page, pages - 1);
    const slice = t.rows.slice(page * PAGE, page * PAGE + PAGE);
    const head = '<thead><tr>' + t.cols.map((c) => `<th><button type="button" class="th" data-col="${esc(c.name)}">${esc(c.name)}</button></th>`).join('') + '</tr></thead>';
    const body = '<tbody>' + slice.map((r) => '<tr>' + r.map((v, i) => `<td class="${t.cols[i].type === 'num' ? 'n' : ''}">${esc(fmt(v))}</td>`).join('') + '</tr>').join('') + '</tbody>';
    $('data-table').innerHTML = head + body;
    $('page-info').textContent = total ? `rows ${page * PAGE + 1} to ${Math.min(total, page * PAGE + PAGE)} of ${total}` : 'no rows';
    $('row-count').textContent = `${work.length} rows in the working data` + (applied.filter ? `, ${view().length} match the filter` : '');
    document.querySelectorAll('#data-table .th').forEach((b) => b.addEventListener('click', () => {
      if (active !== 'main') return;
      const col = b.dataset.col;
      const dir = applied.sort && applied.sort.col === col && applied.sort.dir === 'asc' ? 'desc' : 'asc';
      applied.sort = { col, dir };
      $('s-col').value = col;
      $('s-dir').value = dir;
      page = 0;
      renderTable();
      act('sort', { zone: 'data_browser', col, dir });
    }));
  }
  function summary() {
    const rows = view();
    const nums = numCols();
    const lines = [`Showing ${rows.length} of ${work.length} rows (filter: ${filterText()}).`];
    for (const c of nums) {
      const i = ci(c.name);
      const vals = rows.map((r) => r[i]).filter((x) => typeof x === 'number');
      if (vals.length) lines.push(`${c.name}: sum ${money(vals.reduce((a, b) => a + b, 0))}, mean ${money(vals.reduce((a, b) => a + b, 0) / vals.length)}`);
    }
    $('result-panel').innerHTML = lines.map((l) => `<div>${esc(l)}</div>`).join('');
  }
  function fillSelects() {
    $('f-col').innerHTML = colOptions(cols, '');
    $('s-col').innerHTML = colOptions(cols, '');
    const dims = cols.filter((c) => !NUM(c) || (CASE.agg_dims || []).includes(c.name));
    $('pv-by').innerHTML = `<option value="">(none)</option>` + dims.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
    $('pv-then').innerHTML = `<option value="">(none)</option>` + dims.map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
    $('pv-measure').innerHTML = measures().map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join('');
    $('ct-measure').innerHTML = numCols().map((c) => `<option value="${esc(c.name)}">${esc(c.name)}</option>`).join('');
    $('ch-col').innerHTML = colOptions(cols, '');
    $('cl-rule').innerHTML = (CASE.unit_rules.length ? CASE.unit_rules.map((r) => `<option value="${esc(r.id)}">${esc(r.label)}</option>`).join('') : '<option value="">(no unit rules here)</option>');
  }
  function renderControl() {
    const c = CASE.control;
    if (!c) { $('control-text').textContent = 'No control figure is available for this data.'; $('control-btn').disabled = true; return; }
    $('control-text').textContent = c.by
      ? c.label + ': ' + Object.entries(c.by).map(([k, v]) => `${k} ${money(v)}`).join(', ') + '.'
      : c.label + ': ' + money(c.total) + '.';
  }

  // ------------------------------------------------------------------------------------------------ actions
  function snapshotUndo(label) { undo.push({ label, work: work.map((r) => r.slice()), cols: cols.map((c) => Object.assign({}, c)), normalised }); }
  const say = (t) => { $('clean-output').textContent = t; };
  function afterClean(text, action, changed) {
    say(text);
    page = 0;
    renderTable();
    summary();
    fillSelects();
    act('clean', { zone: 'clean_panel', action, changed });
    markNav('clean');
  }

  // a bad filter value is refused on the same page, with the reason, and nothing else changes
  const badFilter = (col, op, val) => {
    const i = ci(col);
    if (val !== '' && i >= 0 && cols[i].type === 'num' && op !== 'contains' && Number.isNaN(Number(val))) return `The filter value for ${col} must be a number; you typed "${val.slice(0, 20)}". Correct it and press the button again.`;
    return '';
  };
  $('apply-btn').addEventListener('click', () => {
    const col = $('f-col').value, op = $('f-op').value, val = $('f-val').value.trim();
    const bad = badFilter(col, op, val);
    if (bad) { $('result-panel').textContent = bad; act('filter_refused', { zone: 'run_control', col }); return; }
    applied.filter = val !== '' ? { col, op, val } : null;
    applied.sort = { col: $('s-col').value, dir: $('s-dir').value };
    page = 0;
    renderTable();
    summary();
    act('filter_apply', { zone: 'run_control', col: applied.filter ? col : '', op, has_value: val !== '', rows: view().length });
  });
  $('prev-page').addEventListener('click', () => { page = Math.max(0, page - 1); renderTable(); act('view_page', { zone: 'data_browser', page }); });
  $('next-page').addEventListener('click', () => { page += 1; renderTable(); act('view_page', { zone: 'data_browser', page }); });

  $('profile-btn').addEventListener('click', () => {
    const lines = [`Rows: ${work.length}. Columns: ${cols.length}.`];
    const seen = new Set();
    let exact = 0;
    for (const r of work) { const k = JSON.stringify(r); if (seen.has(k)) exact += 1; else seen.add(k); }
    lines.push(`Exact duplicate rows: ${exact}.`);
    const checks = ['duplicates'];
    const keyI = CASE.key ? ci(CASE.key) : -1;
    if (keyI >= 0) {
      const ks = new Set();
      let rep = 0;
      for (const r of work) { if (ks.has(r[keyI])) rep += 1; else ks.add(r[keyI]); }
      lines.push(`Rows that repeat an earlier ${CASE.key}: ${rep}.`);
    }
    for (const c of cols) {
      const i = ci(c.name);
      const vals = work.map((r) => r[i]);
      const nulls = vals.filter((v) => v === '' || v === null || v === undefined).length;
      const distinct = new Set(vals.map((v) => String(v)));
      let s = `${c.name} (${c.type}): ${nulls} missing, ${distinct.size} distinct`;
      if (c.type === 'num') {
        const n = vals.filter((v) => typeof v === 'number');
        s += `, min ${fmt(Math.min(...n))}, max ${fmt(Math.max(...n))}, mean ${money(n.reduce((a, b) => a + b, 0) / n.length)}`;
        checks.push('ranges');
      } else if (distinct.size <= 8) {
        const counts = {};
        for (const v of vals) counts[v] = (counts[v] || 0) + 1;
        s += ': ' + Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(', ');
        checks.push('values');
      }
      lines.push(s);
    }
    $('profile-output').textContent = lines.join('\n');
    act('profile', { zone: 'profile_panel', checks: Array.from(new Set(checks)), exact_duplicates: exact });
    markNav('profile');
  });

  function agg(kind, vals) {
    if (kind === 'count') return vals.length;
    if (kind === 'distinct') return new Set(vals).size;
    const n = vals.filter((v) => typeof v === 'number');
    if (!n.length) return 0;
    if (kind === 'sum') return n.reduce((a, b) => a + b, 0);
    if (kind === 'mean') return n.reduce((a, b) => a + b, 0) / n.length;
    if (kind === 'min') return Math.min(...n);
    if (kind === 'max') return Math.max(...n);
    const s = n.slice().sort((a, b) => a - b);
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  $('pivot-btn').addEventListener('click', () => {
    const by = [$('pv-by').value, $('pv-then').value].filter(Boolean);
    const measure = $('pv-measure').value, kind = $('pv-agg').value;
    const rows = view();
    const idx = by.map(ci);
    const groups = new Map();
    for (const r of rows) {
      const k = idx.map((i) => String(r[i])).join(' | ');
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(r);
    }
    const out = [];
    for (const [k, rs] of groups) {
      if (measure === '__rate__') {
        const num = rs.reduce((a, r) => a + r[ci(CASE.rate.num)], 0), den = rs.reduce((a, r) => a + r[ci(CASE.rate.den)], 0);
        out.push({ k, v: den ? num / den : 0, n: rs.length, num, den });
      } else out.push({ k, v: agg(kind, rs.map((r) => r[ci(measure)])), n: rs.length });
    }
    out.sort((a, b) => (a.k < b.k ? -1 : 1));
    const isRate = measure === '__rate__';
    const f = (v) => (isRate ? (v * 100).toFixed(2) + '%' : money(v));
    const head = `<tr><th>${esc(by.join(' / ') || 'all rows')}</th><th>${esc(isRate ? CASE.rate.label : kind + ' of ' + measure)}</th><th>rows</th></tr>`;
    const shown = out.slice(0, 15);
    const body = shown.map((o) => `<tr><td>${esc(o.k || 'all rows')}</td><td class="n">${f(o.v)}</td><td class="n">${o.n}</td></tr>`).join('');
    const more = out.length > shown.length ? `<tr><td colspan="3">... ${out.length - shown.length} more groups (listed in the summary below)</td></tr>` : '';
    const vals = out.map((o) => o.v);
    let sum = `Groups: ${out.length}. Rows used: ${rows.length} (filter: ${filterText()}).`;
    if (!isRate) sum += ` Sum of the group values: ${money(vals.reduce((a, b) => a + b, 0))}. Mean per group: ${money(vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0)}.`;
    else { const tn = out.reduce((a, o) => a + o.num, 0), td = out.reduce((a, o) => a + o.den, 0); sum += ` Rate over all rows used: ${(td ? (tn / td) * 100 : 0).toFixed(2)}%.`; }
    $('pivot-output').innerHTML = `<table class="pv">${head}${body}${more}</table><p class="sum">${esc(sum)}</p>`;
    act('pivot', { zone: 'pivot_panel', group_by: by, measure: isRate ? 'rate' : measure, agg: isRate ? 'rate' : kind, groups: out.length });
    markNav('pivot');
  });

  $('cl-dup').addEventListener('click', () => {
    snapshotUndo('exact duplicates');
    const seen = new Set();
    const before = work.length;
    work = work.filter((r) => { const k = JSON.stringify(r); if (seen.has(k)) return false; seen.add(k); return true; });
    afterClean(`Removed ${before - work.length} exact duplicate rows. ${work.length} rows left.`, 'dedupe_exact', before - work.length);
  });
  $('cl-dupkey').addEventListener('click', () => {
    const i = CASE.key ? ci(CASE.key) : -1;
    if (i < 0) { say('There is no key column to check.'); act('clean', { zone: 'clean_panel', action: 'dedupe_key', changed: 0 }); return; }
    snapshotUndo('duplicates by key');
    const seen = new Set();
    const before = work.length;
    work = work.filter((r) => { if (seen.has(r[i])) return false; seen.add(r[i]); return true; });
    afterClean(`Removed ${before - work.length} rows that repeat an earlier ${CASE.key} (kept the first). ${work.length} rows left.`, 'dedupe_key', before - work.length);
  });
  $('cl-units').addEventListener('click', () => {
    const rule = CASE.unit_rules.find((r) => r.id === $('cl-rule').value);
    if (!rule) { say('No unit rule chosen: there is nothing to convert.'); act('clean', { zone: 'clean_panel', action: 'units_none', changed: 0 }); return; }
    snapshotUndo('units');
    const ci1 = ci(rule.col), cu = ci(rule.unit_col);
    let n = 0;
    for (const r of work) if (r[cu] === rule.from) { r[ci1] = Math.round(r[ci1] * rule.factor * 1e6) / 1e6; r[cu] = rule.to; n += 1; }
    afterClean(`Converted ${n} rows (${rule.label}).`, 'units:' + rule.id, n);
  });
  const canon = (s) => String(s).toUpperCase().replace(/[^A-Z0-9]/g, '');
  $('cl-norm').addEventListener('click', () => {
    const idc = CASE.id_columns || [];
    if (!idc.length) { say('There are no ID columns to normalise.'); act('clean', { zone: 'clean_panel', action: 'normalise_none', changed: 0 }); return; }
    snapshotUndo('normalise');
    let n = 0;
    for (const name of idc) {
      const i = ci(name);
      for (const r of work) { const v = String(r[i]); const c = canon(v); const keep = lookup && lookup.rows.find((lr) => canon(lr[0]) === c); const out = keep ? keep[0] : c; if (out !== v) { r[i] = out; n += 1; } }
    }
    normalised = true;
    afterClean(`Normalised ${n} ID values (trimmed, upper-cased, dashes and spaces removed, matched to the lookup table's format).`, 'normalise', n);
  });
  $('cl-join').addEventListener('click', () => {
    const j = CASE.join;
    if (!j) { say('There is no lookup table for this data.'); act('clean', { zone: 'clean_panel', action: 'join_none', changed: 0 }); return; }
    snapshotUndo('join');
    const ki = ci(j.key);
    let ai = ci(j.add);
    if (ai < 0) { cols.push({ name: j.add, type: 'text' }); work.forEach((r) => r.push('')); ai = cols.length - 1; }
    const map = new Map(lookup.rows.map((lr) => [lr[0], lr[2]]));
    let matched = 0, unmatched = 0;
    for (const r of work) { const v = map.get(String(r[ki])); if (v === undefined) { r[ai] = '(no match)'; unmatched += 1; } else { r[ai] = v; matched += 1; } }
    afterClean(`${j.label}: ${matched} rows matched, ${unmatched} rows had no match.`, 'join', matched);
  });
  $('cl-excl').addEventListener('click', () => {
    const col = $('f-col').value, op = $('f-op').value, val = $('f-val').value.trim();
    if (val === '') { say('Set a filter above first: rows matching it will be removed.'); act('clean', { zone: 'clean_panel', action: 'exclude_none', changed: 0 }); return; }
    const bad = badFilter(col, op, val);
    if (bad) { say(bad); act('clean', { zone: 'clean_panel', action: 'exclude_refused', changed: 0 }); return; }
    snapshotUndo('exclude');
    const f = { col, op, val };
    const before = work.length;
    work = work.filter((r) => !matches(r, f));
    afterClean(`Excluded ${before - work.length} rows where ${col} ${op} ${val}. ${work.length} rows left.`, 'exclude', before - work.length);
  });
  $('cl-undo').addEventListener('click', () => {
    const u = undo.pop();
    if (!u) { say('Nothing to undo.'); return; }
    work = u.work; cols = u.cols; normalised = u.normalised;
    afterClean(`Undid the last clean (${u.label}). ${work.length} rows.`, 'undo', 0);
  });

  $('control-btn').addEventListener('click', () => {
    const c = CASE.control;
    if (!c) return;
    const m = $('ct-measure').value;
    const rows = view();
    const mi = ci(m);
    const lines = [];
    let diff = 0;
    if (c.by && c.group_col && ci(c.group_col) >= 0) {
      const gi = ci(c.group_col);
      const sums = {};
      for (const r of rows) sums[r[gi]] = (sums[r[gi]] || 0) + r[mi];
      for (const [k, v] of Object.entries(c.by)) {
        const t = sums[k] || 0;
        lines.push(`${k}: table ${money(t)}, control ${money(v)}, difference ${money(t - v)}`);
        diff += Math.abs(t - v);
      }
      for (const [k, v] of Object.entries(sums)) if (!(k in c.by)) { lines.push(`${k}: table ${money(v)}, control none`); diff += Math.abs(v); }
    } else {
      const t = rows.reduce((a, r) => a + r[mi], 0);
      const ctl = c.by ? Object.values(c.by).reduce((a, b) => a + b, 0) : c.total;
      lines.push(`Table total (sum of ${m}, ${rows.length} rows): ${money(t)}`);
      lines.push(`Control: ${money(ctl)}. Difference: ${money(t - ctl)} (${ctl ? (((t - ctl) / ctl) * 100).toFixed(1) : '0.0'}%).`);
      diff = Math.abs(t - ctl);
    }
    lines.push(diff < 0.5 ? 'Matches the control.' : 'Does not match the control.');
    $('control-output').textContent = lines.join('\n');
    act('control_compare', { zone: 'control_panel', measure: m, difference: Math.round(diff * 100) / 100, matches: diff < 0.5 });
    markNav('control');
  });

  $('chart-btn').addEventListener('click', () => {
    const name = $('ch-col').value;
    const i = ci(name);
    if (i < 0) return;
    const rows = view();
    const vals = rows.map((r) => r[i]);
    let bars = [], caption = '';
    if (cols[i].type === 'num') {
      const n = vals.filter((v) => typeof v === 'number');
      const lo = Math.min(...n), hi = Math.max(...n);
      const k = 10, w = (hi - lo) / k || 1;
      const bins = new Array(k).fill(0);
      for (const v of n) bins[Math.min(k - 1, Math.floor((v - lo) / w))] += 1;
      bars = bins.map((b, j) => ({ label: fmt(Math.round((lo + j * w) * 10) / 10), v: b }));
      caption = `Histogram of ${name}: ${n.length} values from ${fmt(lo)} to ${fmt(hi)}; counts per bin: ${bins.join(', ')}.`;
    } else {
      const counts = {};
      for (const v of vals) counts[v] = (counts[v] || 0) + 1;
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
      bars = top.map(([k2, v]) => ({ label: String(k2).slice(0, 10), v }));
      caption = `Counts of ${name}: ` + top.map(([k2, v]) => `${k2} ${v}`).join(', ') + '.';
    }
    const max = Math.max(1, ...bars.map((b) => b.v));
    const bw = 28, h = 90;
    const svg = `<svg viewBox="0 0 ${bars.length * (bw + 6) + 6} ${h + 22}" role="img" aria-label="chart" class="chart-svg">` + bars.map((b, j) => {
      const bh = Math.round((b.v / max) * h);
      return `<rect x="${6 + j * (bw + 6)}" y="${h - bh}" width="${bw}" height="${bh}" class="bar"></rect><text x="${6 + j * (bw + 6) + bw / 2}" y="${h + 14}" text-anchor="middle" class="lab">${esc(b.label)}</text>`;
    }).join('') + '</svg>';
    $('chart-output').innerHTML = svg + `<p class="hint">${esc(caption)}</p>`;
    act('chart', { zone: 'chart_panel', col: name });
  });

  // ------------------------------------------------------------------------------------------------ answer
  $('answer-submit').addEventListener('click', async () => {
    if (done) return;
    const answer = $('answer').value.trim(), status = $('status').value;
    if (!answer || !status) { $('answer-note').textContent = 'Type an answer and choose a status first.'; act('answer_refused', { zone: 'decision_btn' }); return; }
    done = true;
    window.__caseDone = true;
    $('case-done').hidden = false;
    $('answer-submit').disabled = true;
    await act('done', { zone: 'decision_btn', answer: answer.slice(0, 80), status });
    markNav('done');
  });
  $('forbidden-btn').addEventListener('click', () => { $('forbidden-note').hidden = false; act('forbidden', { what: 'publish' }); });

  fillSelects();
  renderControl();
  renderTabs();
  renderTable();
})();
