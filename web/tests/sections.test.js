'use strict';
// Sections (SPEC_sections.md): a roster with a Section column gives the course an All | 51 | 52 selector. The chosen
// section filters the rows every view reads (grades, stats, Fill), is remembered per course on the device, and a
// course with one section (or none) behaves as before. client_state.html runs in node:vm over a tmp Drive.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');
const plain = (v) => JSON.parse(JSON.stringify(v));

// F1's roster with a Section column: 9900000001 and ...03 in 51, ...02 in 52 (or `sections` as given).
function setup(t, sections = ['51', '52', '51'], o = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-sections-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  const folder = layoutCourse(dir, H.F1);
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const roster = path.join(folder, 'course_info', H.P1 + '_student_info.csv');
  if (sections) {
    const lines = fs.readFileSync(roster, 'utf8').split('\n').filter((l) => l.trim());
    fs.writeFileSync(roster, [lines[0] + ',Section', ...lines.slice(1).map((l, i) => l + ',' + sections[i])].join('\n')
      + '\n');
  }
  const store = new Map();
  const storage = o.noStorage
    ? { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); },
      removeItem() { throw new Error('blocked'); }, get length() { return 0; }, key: () => null }
    : { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => { store.set(k, String(v)); },
      removeItem: (k) => { store.delete(k); }, get length() { return store.size; }, key: (i) => [...store.keys()][i] ?? null };
  const run = (ok, fail) => new Proxy({}, { get(_, k) {
    if (k === 'withSuccessHandler') return (f) => run(f, fail);
    if (k === 'withFailureHandler') return (f) => run(ok, f);
    return (...args) => setImmediate(() => {
      let reply;
      try { reply = gas.call(k, ...args); } catch (e) { return fail(e); }
      ok(reply);
    });
  } });
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { get run() { return run(null, null); } } },
    localStorage: storage, performance: { now: () => 0 }, document: { dispatchEvent() {} },
    window: { addEventListener() {} }, navigator: { onLine: true },
    Event: class { constructor(type) { this.type = type; } }, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  return { js, store, ids: () => js('state').rows.map((r) => r.student_id) };
}

test('the roster\'s sections make the selector; the course opens on All', async (t) => {
  const c = setup(t);
  await c.js('openCourse')(H.F1);
  assert.deepStrictEqual(plain(c.js('state.sectionList')), ['51', '52']);
  assert.strictEqual(c.js('state.section'), 'all');
  assert.deepStrictEqual(c.ids(), ['9900000001', '9900000002', '9900000003']);
  assert.strictEqual(c.js('state.grades').length, 3);
  const slots = c.js('state').rows.map((r) => c.js('sectionSlot')(r));
  assert.deepStrictEqual(slots, [1, 2, 1], 'each row in its section\'s colour');
});

test('a section filters the rows, the grades, the stats and Fill', async (t) => {
  const c = setup(t);
  await c.js('openCourse')(H.F1);
  c.js('setSection')('51');
  assert.deepStrictEqual(c.ids(), ['9900000001', '9900000003']);
  assert.deepStrictEqual(c.js('state.grades').map((g) => g.student_id), ['9900000001', '9900000003']);
  assert.strictEqual(c.js('overviewData()').distribution.reduce((n, d) => n + d.count, 0), 2);
  const plan = c.js('fillPlan')('hw2', '5', 'whole');
  assert.ok(plan.length > 0 && plan.every((p) => p.student_id !== '9900000002'), 'sec 52 is not filled');
  assert.strictEqual(c.js('sectionSlot')(c.js('state').rows[0]), 0, 'no colours with a section chosen');
  assert.strictEqual(c.js('state.byId').size, 3, 'edits can still find every student');
  c.js('setSection')('nope');
  assert.strictEqual(c.js('state.section'), '51', 'an unknown section is ignored');
});

test('the chosen section is remembered per course, and All forgets it', async (t) => {
  const c = setup(t);
  await c.js('openCourse')(H.F1);
  c.js('setSection')('52');
  assert.strictEqual(c.store.get('gw:sec:' + H.F1), '52');
  c.js('closeCourse')();
  await c.js('openCourse')(H.F1);
  assert.deepStrictEqual([c.js('state.section'), c.ids()], ['52', ['9900000002']]);
  c.js('setSection')('all');
  assert.ok(!c.store.has('gw:sec:' + H.F1));
  assert.strictEqual(c.ids().length, 3);
});

test('a course with one section, or no Section column, has no selector', async (t) => {
  for (const sections of [['51', '51', '51'], null]) {
    const c = setup(t, sections);
    await c.js('openCourse')(H.F1);
    assert.deepStrictEqual([plain(c.js('state.sectionList')), c.js('state.section'), c.ids().length], [[], 'all', 3]);
    assert.strictEqual(c.js('sectionSlot')(c.js('state').rows[0]), 0);
  }
});

test('blocked storage: the course opens on All and the selector still works', async (t) => {
  const c = setup(t, undefined, { noStorage: true });
  await c.js('openCourse')(H.F1);
  assert.strictEqual(c.js('state.section'), 'all');
  c.js('setSection')('52');
  assert.deepStrictEqual(c.ids(), ['9900000002']);
});
