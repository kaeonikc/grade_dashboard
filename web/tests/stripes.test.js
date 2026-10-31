'use strict';
// Striped rows in the grids (SPEC_name_stripes.md N3): every second shown row, counted afresh under each section
// heading in All, in the colour of the section shown (tableSlot) or of each row's section in All.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');

// client_state with sec 51 (28 students, 6800000001…28) and sec 52 (27, 6800000101…127), showing `section`.
function page(section, sectionList = ['51', '52']) {
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { run: {} } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {}, length: 0, key: () => null },
    performance: { now: () => 0 }, document: { dispatchEvent() {} }, window: { addEventListener() {} },
    navigator: { onLine: true }, Event: class { constructor(t) { this.type = t; } }, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  const rows = [];
  const sections = new Map();
  for (const [sec, n, base] of [['51', 28, 6800000001], ['52', 27, 6800000101]]) {
    for (let i = 0; i < n; i++) {
      const id = String(base + i);
      rows.push({ student_id: id, name: 'S ' + id });
      sections.set(id, sec);
    }
  }
  const state = js('state');
  state.sectionList = sectionList;
  state.sections = sections;
  state.section = section;
  const of = (sec) => rows.filter((r) => sections.get(r.student_id) === sec);
  const striped = (list, shown = () => true) => {
    const set = js('stripes')(list, shown);
    return list.filter((r) => shown(r)).map((r) => set.has(r.student_id));
  };
  return { js, rows, of, striped };
}

const alternate = (n) => Array.from({ length: n }, (_, i) => i % 2 === 1);

test('one section: every second student is striped', () => {
  const p = page('51');
  const rows = p.of('51');
  assert.deepStrictEqual(p.striped(rows), alternate(28));
  const set = p.js('stripes')(rows, () => true);
  assert.ok(set.has('6800000002') && set.has('6800000028') && !set.has('6800000001'));
});

test('hidden rows do not count: the shown ones still alternate', () => {
  const p = page('51');
  const rows = p.of('51');
  const keep = new Set(['6800000003', '6800000004', '6800000009', '6800000010', '6800000017']);
  const shown = (r) => keep.has(r.student_id);
  assert.deepStrictEqual(p.striped(rows, shown), alternate(5));
  const set = p.js('stripes')(rows, shown);
  assert.ok([...set].every((id) => keep.has(id)), 'a hidden row is never striped');
});

test('All: each section block starts its own stripes', () => {
  const p = page('all');
  const set = p.js('stripes')(p.rows, () => true);
  assert.ok(!set.has('6800000001'), 'the first row under Sec 51 is plain');
  assert.ok(!set.has('6800000101'), 'the first row under Sec 52 is plain, though Sec 51 ended on a plain row');
  assert.deepStrictEqual(p.striped(p.rows), alternate(28).concat(alternate(27)));
});

test('At risk only: the few shown rows alternate within their blocks', () => {
  const p = page('all');
  const keep = new Set(['6800000005', '6800000020', '6800000110']);
  assert.deepStrictEqual(p.striped(p.rows, (r) => keep.has(r.student_id)), [false, true, false]);
});

test('stripes follow the order given, not the roster order', () => {
  const p = page('51');
  const sorted = p.of('51').slice().reverse();
  const set = p.js('stripes')(sorted, () => true);
  assert.ok(!set.has('6800000028') && set.has('6800000027'), 'the first row shown (the last on the roster) is plain');
  assert.deepStrictEqual(p.striped(sorted), alternate(28));
});

test('tableSlot: the colour of the one section shown', () => {
  assert.strictEqual(page('51').js('tableSlot()'), 1);
  assert.strictEqual(page('52').js('tableSlot()'), 2);
  assert.strictEqual(page('all').js('tableSlot()'), 0, 'All: each row has its own colour');
  assert.strictEqual(page('all', []).js('tableSlot()'), 0, 'no sections: the app blue');
});
