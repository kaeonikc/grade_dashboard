'use strict';
// The status lines (SPEC_status_line.md): one line under the course name (class time of the section shown, students
// at risk, edits not pulled, how old the push is) and one under the title on the course list. client_state.html runs
// in node:vm over a tmp Drive: F1 has three students and attendance sessions 13, 20 and 27 Jan 2027.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, golden, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');
const WHEN = { 51: { day: 'ศ.', time: '08:30-12:30' }, 52: { day: 'ศ.', time: '13:30-17:30' } };

// F1 with sec 51 (…01, …03) and 52 (…02) and class times, or as pushed with `flat`.
async function open(t, o = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-head-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  const folder = layoutCourse(dir, H.F1, o.flat ? {} : { course: { ...golden(H.F1), sections: WHEN } });
  if (!o.flat) {
    const roster = path.join(folder, 'course_info', H.P1 + '_student_info.csv');
    const lines = fs.readFileSync(roster, 'utf8').split('\n').filter((l) => l.trim());
    const sec = ['51', '52', '51'];
    fs.writeFileSync(roster, [lines[0] + ',Section', ...lines.slice(1).map((l, i) => l + ',' + sec[i])].join('\n') + '\n');
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

const EVERYONE = ['9900000001', '9900000002', '9900000003'];

// Gives every student `code` in every session as an unsaved edit: A puts them at risk, P clears them.
function markAll(js, code) {
  for (const id of EVERYONE) {
    for (const s of js('sessions()')) js('setCell')(js('state.byId').get(id), s.name, code);
  }
}

test('one section shows its class time, first', async (t) => {
  const js = await open(t);
  js('setSection')('51');
  assert.match(js('headSummary()'), /^ศ\. 08:30-12:30 · /);
  js('setSection')('52');
  assert.match(js('headSummary()'), /^ศ\. 13:30-17:30 · /);
});

test('All and a course without sections have no class time', async (t) => {
  const js = await open(t);
  js('setSection')('all');
  assert.doesNotMatch(js('headSummary()'), /\d\d:\d\d-/);
  const flat = await open(t, { flat: true });
  assert.doesNotMatch(flat('headSummary()'), /\d\d:\d\d-/);
});

test('at risk counts the section shown and follows unsaved edits', async (t) => {
  const js = await open(t);
  js('setSection')('all');
  markAll(js, 'P');
  assert.doesNotMatch(js('headSummary()'), /at risk/);
  markAll(js, 'A');
  assert.match(js('headSummary()'), /\b3 at risk\b/);
  js('setSection')('51');
  assert.match(js('headSummary()'), /\b2 at risk\b/);
  js('setSection')('52');
  assert.match(js('headSummary()'), /\b1 at risk\b/);
});

test('in All, a session only one section has held is no absence for the other', async (t) => {
  const js = await open(t);
  js('setSection')('all');
  const undated = js('sessions()').map((s) => s.name);
  js('state.open.course').columns.filter((c) => undated.includes(c.name)).forEach((c, i) => { c.header = 'a' + (i + 1); });
  for (const id of EVERYONE) for (const name of undated) js('setCell')(js('state.byId').get(id), name, '');
  for (const name of undated) {
    js('setCell')(js('state.byId').get('9900000001'), name, 'P');
    js('setCell')(js('state.byId').get('9900000003'), name, 'A');
  }
  const all = js('attStats()').students;
  assert.strictEqual(all.get('9900000002').held, 0, 'sec 52 has held nothing');
  assert.strictEqual(all.get('9900000002').atRisk, false);
  assert.strictEqual(all.get('9900000003').atRisk, true);
  assert.match(js('headSummary()'), /^1 at risk · /);
});

test('nothing at risk and nothing to pull are left out; Pushed comes last', async (t) => {
  const js = await open(t);
  markAll(js, 'P');
  js('setSection')('all');
  assert.strictEqual(js('headSummary()'), 'Pushed ' + js('Journal.fmt.fmtAgo')(js('state.open.push.pushed_at'), js('state.now')));
});

test('edits not pulled sit before Pushed', async (t) => {
  const js = await open(t);
  js('state.open.journal').unpulled = 11;
  assert.match(js('headSummary()'), /11 edits not pulled · Pushed .+ ago$/);
  js('state.open.journal').unpulled = 1;
  assert.match(js('headSummary()'), /1 edit not pulled · Pushed .+ ago$/);
});

test('the list line adds up the courses and their edits', async (t) => {
  const js = await open(t);
  const list = (a) => js('listSummary')(a);
  assert.strictEqual(list([{ unpulled: 0 }]), '1 course');
  assert.strictEqual(list([{ unpulled: 0 }, { unpulled: 0 }, {}]), '3 courses');
  assert.strictEqual(list([{ unpulled: 11 }, { unpulled: 51 }, { unpulled: 0 }]), '3 courses · 62 edits not pulled');
  assert.strictEqual(list([{ unpulled: 1 }]), '1 course · 1 edit not pulled');
});
