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
const { createGas, golden, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');
const plain = (v) => JSON.parse(JSON.stringify(v));

// F1's roster with a Section column: 9900000001 and ...03 in 51, ...02 in 52 (or `sections` as given).
function setup(t, sections = ['51', '52', '51'], o = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-sections-'));
  const gas = createGas({ drive: dir, now: o.now || '2027-01-20T09:15:02+07:00' });
  const folder = layoutCourse(dir, H.F1, o.schedules ? { course: { ...golden(H.F1), sections: o.schedules } } : {});
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
  assert.deepStrictEqual(c.ids(), ['9900000001', '9900000003', '9900000002'], 'All: sec 51\'s block, then 52\'s');
  assert.strictEqual(c.js('state.grades').length, 3);
  const slots = c.js('state').rows.map((r) => c.js('sectionSlot')(r));
  assert.deepStrictEqual(slots, [1, 1, 2], 'each row in its section\'s colour');
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

// ---- Revision 2 (SPEC_sections.md R5, R7, R2) ----------------------------------------------------------------------
test('All is in section blocks, each with its heading; a section shows none', async (t) => {
  const c = setup(t, ['52', '51', '']);
  await c.js('openCourse')(H.F1);
  assert.deepStrictEqual(c.ids(), ['9900000002', '9900000001', '9900000003'], '51, then 52, then no section');
  const blocks = plain(c.js('sectionBlocks(state.rows)'));
  assert.deepStrictEqual(blocks, [{ start: 0, count: 1, section: '51', slot: 1 }, { start: 1, count: 1, section: '52', slot: 2 },
    { start: 2, count: 1, section: '', slot: 0 }]);
  assert.deepStrictEqual(blocks.map((b) => c.js('sectionTitle')(b)), ['Sec 51 · 1 student', 'Sec 52 · 1 student',
    'No section · 1 student']);
  c.js('setSection')('52');
  assert.deepStrictEqual(plain(c.js('sectionBlocks(state.rows)')), []);
});

test('a one-section course keeps its order and has no headings', async (t) => {
  const c = setup(t, ['51', '51', '51']);
  await c.js('openCourse')(H.F1);
  assert.deepStrictEqual(c.ids(), ['9900000001', '9900000002', '9900000003']);
  assert.deepStrictEqual(plain(c.js('sectionBlocks(state.rows)')), []);
});

test('pickSection: the section in class (from 30 minutes before), else the last choice, else All', async (t) => {
  const c = setup(t);
  await c.js('openCourse')(H.F1);
  const course = { sections: { 51: { day: 'ศ.', time: '08:30-12:30' }, 52: { day: 'ศ.', time: '13:30-17:30' } } };
  const pick = (iso, kept = 'all') => c.js('pickSection')(course, iso, kept);
  assert.strictEqual(pick('2026-10-30T09:00:00+07:00'), '51', 'Friday morning');
  assert.strictEqual(pick('2026-10-30T08:00:00+07:00'), '51', '30 minutes early');
  assert.strictEqual(pick('2026-10-30T07:59:00+07:00'), 'all');
  assert.strictEqual(pick('2026-10-30T12:30:00+07:00'), 'all', 'sec 51 has ended, 52 is an hour away');
  assert.strictEqual(pick('2026-10-30T13:15:00+07:00'), '52');
  assert.strictEqual(pick('2026-11-02T09:00:00+07:00', '52'), '52', 'Monday: the last choice');
  assert.strictEqual(pick('2026-11-02T09:00:00+07:00', 'gone'), 'all');
  assert.strictEqual(c.js('pickSection')({ sections: { 51: { day: '?', time: 'soon' } } }, '2026-10-30T09:00:00+07:00',
    'all'), 'all', 'a schedule it can\'t read is skipped');
  assert.strictEqual(c.js('pickSection')({}, '2026-10-30T09:00:00+07:00', '51'), '51', 'no schedules pushed');
  assert.strictEqual(c.js('inClass')({ day: 'จ. พฤ.', time: '13.00-15.00' }, '2026-10-29T14:00:00+07:00'), true,
    'two days, dots in the time');
});

test('the course opens on the section in class; a chip tapped by hand stays through a reload', async (t) => {
  // The fake server's clock: Wednesday 20 Jan 2027, 09:15
  const c = setup(t, undefined, { schedules: { 51: { day: 'พ.', time: '09:00-12:00' }, 52: { day: 'พ.', time: '13:00-16:00' } } });
  await c.js('openCourse')(H.F1);
  assert.strictEqual(c.js('state.section'), '51');
  assert.deepStrictEqual(c.ids(), ['9900000001', '9900000003']);
  c.js('setSection')('all');
  await c.js('reloadCourse')();
  assert.strictEqual(c.js('state.section'), 'all', 'your tap wins until you leave the course');
  c.js('closeCourse')();
  await c.js('openCourse')(H.F1);
  assert.strictEqual(c.js('state.section'), '51', 'opened again in class: the section in class');
});

test('a renamed course carries its draft, UI memory, section and gw:last over', async (t) => {
  const c = setup(t);
  for (const [k, v] of [['gw:draft:2569-2/Old', '{"v":1}'], ['gw:ui:2569-2/Old', '{"tab":"raw"}'], ['gw:sec:2569-2/Old', '52'],
    ['gw:last', '2569-2/Old'], ['gw:ui:2569-2/New', '{"tab":"summary"}']]) c.store.set(k, v);
  c.js('migrateKeys')([{ folder: '2569-2/New', group: '2569-2', renamed_from: ['Old'] }]);
  assert.strictEqual(c.store.get('gw:draft:2569-2/New'), '{"v":1}');
  assert.strictEqual(c.store.get('gw:sec:2569-2/New'), '52');
  assert.strictEqual(c.store.get('gw:last'), '2569-2/New');
  assert.strictEqual(c.store.get('gw:ui:2569-2/New'), '{"tab":"summary"}', 'what the new name has already is kept');
  assert.ok(!c.store.has('gw:draft:2569-2/Old') && !c.store.has('gw:sec:2569-2/Old'));
});
