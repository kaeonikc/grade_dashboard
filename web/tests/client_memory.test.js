'use strict';
// Browser memory (SPEC_discard_and_speed.md D6-D8): client_state.html in node:vm, its google.script.run calls going
// to the real server code over a tmp Drive (gas_fake.js), with a clock the tests move.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const HW = 'data/' + H.P1 + '_homework.csv';
const ALL = [H.F1, H.F2, H.F3, H.F4];
const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');

function setup(t, fixtures) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-client-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  const folders = {};
  for (const f of fixtures) folders[f] = layoutCourse(dir, f);
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));

  const calls = [];
  const store = new Map();
  let clock = Date.parse('2027-01-20T09:15:02+07:00');
  class ClientDate extends Date {
    constructor(...a) { if (a.length) super(...a); else super(clock); }
    static now() { return clock; }
  }
  const run = (ok, fail) => new Proxy({}, { get(_, k) {
    if (k === 'withSuccessHandler') return (f) => run(f, fail);
    if (k === 'withFailureHandler') return (f) => run(ok, f);
    return (...args) => {
      calls.push(k);
      setImmediate(() => {
        let reply;
        try { reply = gas.call(k, ...args); } catch (e) { return fail(e); }
        ok(reply);
      });
    };
  } });
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { get run() { return run(null, null); } } },
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => { store.set(k, String(v)); },
      removeItem: (k) => { store.delete(k); },
    },
    performance: { now: () => clock },
    document: { dispatchEvent() {} },
    window: { addEventListener() {} },
    navigator: { onLine: true },
    Event: class { constructor(type) { this.type = type; } },
    Date: ClientDate, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  return {
    gas, folders, calls, store, js,
    tick: (ms) => { clock += ms; },
    open: (folder) => js('openCourse')(folder),
    cell: (sid, column) => js('state').byId.get(sid).cells[column],
  };
}

test('the course list is kept on the device without student data', async (t) => {
  const c = setup(t, [H.F1, H.F2]);
  await c.js('loadCourses')();
  const saved = JSON.parse(c.store.get('gw:courses'));
  assert.strictEqual(saved.v, 1);
  assert.strictEqual(saved.courses.length, 2);
  assert.deepStrictEqual(Object.keys(saved.courses[0]).sort(), ['available', 'course_id', 'course_name', 'folder',
    'last_saved', 'older_push', 'pushed_at', 'term', 'unpulled']);
  assert.ok(!/99\d{8}/.test(c.store.get('gw:courses')), 'no student ID');
  assert.ok(!c.store.get('gw:courses').includes('นายสมมติ'), 'no student name');
  assert.deepStrictEqual(JSON.parse(JSON.stringify(c.js('courseListCache')().courses)), saved.courses);
});

test('a course opened again within 60 s needs no call; later it opens stale and the recheck unlocks it', async (t) => {
  const c = setup(t, [H.F1]);
  const first = await c.open(H.F1);
  assert.deepStrictEqual([first.reply.ok, first.stale, c.calls.length], [true, false, 1]);
  assert.strictEqual(c.store.get('gw:last'), H.F1);
  c.js('closeCourse')();
  c.tick(59000);
  const again = await c.open(H.F1);
  assert.deepStrictEqual([again.stale, c.calls.length, c.js('state.checking')], [false, 1, false]);
  c.js('closeCourse')();
  c.tick(2000);
  const stale = await c.open(H.F1);
  assert.deepStrictEqual([stale.stale, c.calls.length, c.js('state.checking'), c.js('locked()')], [true, 1, true, true]);
  // another device changes a cell meanwhile
  const f = c.folders[H.F1];
  fs.writeFileSync(path.join(f, HW), fs.readFileSync(path.join(f, HW), 'utf8').replace('ทดสอบ,8,,,8', 'ทดสอบ,8,6,,14'));
  assert.strictEqual(c.cell('9900000001', 'hw2'), '');
  const fresh = await c.js('recheckCourse')();
  assert.strictEqual(fresh.reply.ok, true);
  assert.deepStrictEqual([c.calls.length, c.js('state.checking'), c.js('locked()')], [2, false, false]);
  assert.strictEqual(c.cell('9900000001', 'hw2'), '6');
});

test('a tap while the prefetch is on its way waits for that same call', async (t) => {
  const c = setup(t, [H.F1]);
  c.js('prefetch')(H.F1);
  c.js('prefetch')(H.F1);
  const opened = await c.open(H.F1);
  assert.deepStrictEqual([opened.reply.ok, opened.stale, c.calls], [true, false, ['loadCourse']]);
  c.js('closeCourse')();
  c.js('prefetch')(H.F1);
  assert.strictEqual(c.calls.length, 1, 'a fresh copy is not fetched again');
});

test('memory keeps the 3 courses used last, as they show (saved values included)', async (t) => {
  const c = setup(t, ALL);
  await c.open(H.F1);
  c.js('state').edits.set('x', { student_id: '9900000001', column: 'hw2', value: '9', original: '' });
  const r = await c.js('saveEdits')();
  assert.strictEqual(r.saved.length, 1);
  c.js('closeCourse')();
  const again = await c.open(H.F1);
  assert.strictEqual(c.calls.filter((n) => n === 'loadCourse').length, 1);
  assert.strictEqual(c.cell('9900000001', 'hw2'), '9', 'the save shows on reopening from memory');
  assert.strictEqual(again.reply.journal.unpulled, 1);
  c.js('closeCourse')();
  for (const f of [H.F2, H.F3, H.F4]) {
    await c.open(f);
    c.js('closeCourse')();
  }
  assert.deepStrictEqual([...c.js('state').loaded.keys()], [H.F2, H.F3, H.F4]);
});

test('a reply that is not ok drops the course from memory', async (t) => {
  const c = setup(t, [H.F1]);
  await c.open(H.F1);
  c.js('closeCourse')();
  fs.rmSync(path.join(c.folders[H.F1], 'course.json'));
  c.tick(61000);
  const stale = await c.open(H.F1);
  assert.strictEqual(stale.stale, true);
  const r = await c.js('recheckCourse')();
  assert.deepStrictEqual([r.reply.ok, r.reply.code, r.draft], [false, 'UNAVAILABLE', undefined]);
  assert.strictEqual(c.js('state').loaded.has(H.F1), false);
});
