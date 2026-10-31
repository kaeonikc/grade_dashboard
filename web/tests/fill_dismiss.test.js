'use strict';
// Fill on the attendance grid, and a tap outside that only closes (SPEC_fill_dismiss.md). client_state.html runs in
// node:vm over a tmp Drive: F1 has three students and attendance sessions 13, 20 and 27 Jan 2027.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, golden, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');
const VIEWS = fs.readFileSync(path.join(H.APPS, 'client_views.html'), 'utf8');
const css = H.readText(path.join(H.APPS, 'style.html'));
const WHEN = { 51: { day: 'ศ.', time: '08:30-12:30' }, 52: { day: 'ศ.', time: '13:30-17:30' } };
const SEC = ['51', '52', '51'];

// F1 open at `now`, with sections 51 and 52 unless `flat`.
async function open(t, o = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-fill-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const gas = createGas({ drive: dir, now: o.now || '2027-01-20T09:15:02+07:00' });
  const folder = layoutCourse(dir, H.F1, o.flat ? {} : { course: { ...golden(H.F1), sections: WHEN } });
  if (!o.flat) {
    const roster = path.join(folder, 'course_info', H.P1 + '_student_info.csv');
    const lines = fs.readFileSync(roster, 'utf8').split('\n').filter((l) => l.trim());
    fs.writeFileSync(roster, [lines[0] + ',Section', ...lines.slice(1).map((l, i) => l + ',' + SEC[i])].join('\n') + '\n');
  }
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
    localStorage: { getItem: () => null, setItem() {}, removeItem() {}, length: 0, key: () => null },
    performance: { now: () => 0 }, document: { dispatchEvent() {} }, window: { addEventListener() {} },
    navigator: { onLine: true }, Event: class { constructor(type) { this.type = type; } }, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  await js('openCourse')(H.F1);
  return js;
}

const names = (js) => Array.from(js('sessions()'), (s) => s.name);
const blankAll = (js) => {
  for (const row of Array.from(js('state.allRows'))) for (const n of names(js)) js('setCell')(row, n, '');
};

test('fillSession: today\'s session when there is one', async (t) => {
  const js = await open(t);
  assert.strictEqual(js('fillSession()'), js('todaySession()'));
  assert.ok(js('fillSession()'));
});

test('fillSession: no class today gives the latest held session', async (t) => {
  const js = await open(t, { now: '2027-01-22T09:15:02+07:00' });
  assert.strictEqual(js('todaySession()'), null);
  assert.strictEqual(js('fillSession()'), names(js)[1], '20 Jan is held, 27 Jan is not');
});

test('fillSession: before the first session gives the first', async (t) => {
  const js = await open(t, { now: '2027-01-02T09:15:02+07:00' });
  assert.strictEqual(js('fillSession()'), names(js)[0]);
});

test('fillSession: undated sessions are held once a student has a code there', async (t) => {
  const js = await open(t);
  const cols = Array.from(js('sessions()'));
  ['a1', 'a2', 'a3'].forEach((h, i) => { cols[i].header = h; });
  blankAll(js);
  assert.strictEqual(js('fillSession()'), names(js)[0], 'none held: the first');
  js('setCell')(js('state.allRows')[0], names(js)[1], 'P');
  assert.strictEqual(js('fillSession()'), names(js)[1]);
});

test('fillSession: a course without sessions has none', async (t) => {
  const js = await open(t);
  js('state.open.course').columns = Array.from(js('state.open.course').columns).filter((c) => c.category !== 'attendance');
  assert.strictEqual(js('fillSession()'), null);
});

test('fillScope: All on attendance names both sections and their sizes', async (t) => {
  const js = await open(t);
  js('setSection')('all');
  const col = js('sessions()')[0];
  assert.strictEqual(js('fillScope')(col), 'All sections: 3 students (Sec 51 · 2, Sec 52 · 1)');
});

test('fillScope: nothing with a section chosen, without sections, or on a score column', async (t) => {
  const js = await open(t);
  js('setSection')('51');
  assert.strictEqual(js('fillScope')(js('sessions()')[0]), null);
  js('setSection')('all');
  const score = Array.from(js('state.open.course').columns).find((c) => c.category !== 'attendance');
  assert.strictEqual(js('fillScope')(score), null);
  const flat = await open(t, { flat: true });
  assert.strictEqual(flat('fillScope')(flat('sessions()')[0]), null);
});

test('fillPlan over a session: only empty cells, or the whole column with EA', async (t) => {
  const js = await open(t);
  js('setSection')('all');
  blankAll(js);
  const [one, two, three] = Array.from(js('state.allRows'));
  const name = names(js)[0];
  js('setCell')(one, name, 'A');
  js('setCell')(two, name, 'EA');
  assert.deepStrictEqual(Array.from(js('fillPlan')(name, 'P', 'empty'), (x) => x.student_id), [three.student_id],
    'unsaved values count as filled');
  assert.strictEqual(js('fillPlan')(name, 'P', 'whole').length, 3);
  assert.strictEqual(js('fillPlan')(names(js)[1], '', 'whole').length, 0, 'Clear on a blank session changes nothing');
});

test('the tap-through while typing is gone', () => {
  for (const name of ['keepsEditor', 'editOther']) assert.ok(!VIEWS.includes(name), name);
});

test('one guard handles a tap outside: it closes on pointerup and swallows the click', () => {
  assert.match(VIEWS, /document\.addEventListener\('pointerdown', outsideDown, true\)/);
  assert.match(VIEWS, /document\.addEventListener\('pointerup', outsideUp, true\)/);
  assert.match(VIEWS, /document\.addEventListener\('pointercancel', outsideCancel, true\)/);
  assert.match(VIEWS, /document\.addEventListener\('click', outsideClick, true\)/);
});

test('the attendance grid shows Fill', () => {
  assert.doesNotMatch(css, /\.view-attgrid \.fill-btn/);
});

test('the Fill sheet\'s session menu is at least 16 px, or iOS zooms', () => {
  assert.match(VIEWS, /class: 'col-select fill-session'/);
  assert.doesNotMatch(css, /\.fill-session[^{]*\{[^}]*font-size/);
  assert.match(css, /button, input, select \{ font: inherit; font-size: max\(1rem, 16px\); \}/);
});

test('the phone search box stays usable beside Fill', () => {
  assert.strictEqual(VIEWS.split("cm.clear.hidden = state.search === '';").length, 3, 'when built and on every search');
  assert.match(VIEWS, /cm\.takeToday\.hidden = !t && !WIDE\.matches/);
  assert.match(css, /\.search-row \.search \{ min-width: 4\.5rem; \}/);
  assert.match(css, /\.search-input:placeholder-shown \{ padding-right: 0\.25rem; \}/);
});
