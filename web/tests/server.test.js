'use strict';
// Server harness (web/SPEC.md "Layer 1b"): Code.js + drive.js + the pure modules in node:vm with faked services.
// S2.1-S2.4, S6.5, S6.7, S8.1-S8.3, S8.5, S8.6, S9.1-S9.3, S9.5, S10.1, S10.5, edges 17, 19, 29, 35, 38, trim, logs.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createGas, layoutCourse, DEFAULT_PUSH } = require('./gas_fake.js');
const H = require('./helpers.js');

const NOW = '2027-01-20T09:15:02+07:00';
const HW = 'data/9_ฟิสิกส์จำลอง_homework.csv';
const MID = 'data/9_ฟิสิกส์จำลอง_midterm.csv';
const ATT = 'data/9_ฟิสิกส์จำลอง_attendance.csv';
const S81 = [
  { student_id: '9900000001', column: 'hw2', value: '9', original: '' },
  { student_id: '9900000002', column: 'hw2', value: '8', original: '' },
  { student_id: '9900000002', column: 'midterm_exam', value: '20', original: '18' },
];
const NOTE_PULLED = 'Already pulled to the Mac; use `grader undo` there';

const STUDENT_NAMES = (() => {
  const names = [];
  for (const f of [H.F1, H.F2]) {
    const dir = path.join(H.FIXTURES, f, 'course_info');
    const roster = fs.readdirSync(dir).find((n) => n.endsWith('_student_info.csv'));
    for (const line of H.readText(path.join(dir, roster)).split('\n').slice(1)) {
      const m = line.match(/^\d+,("(?:[^"]|"")*"|[^,]*),/);
      if (m) names.push(m[1].replace(/^"|"$/g, '').replace(/""/g, '"').split(/[ ,]/)[0].replace(/^นาย|^นางสาว/, ''));
    }
  }
  return names.filter((n) => n.length >= 2);
})();

// One harness per test: a tmp "My Drive", the fake services, and a log check at the end.
function setup(t, courses) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-drive-'));
  const gas = createGas({ drive: dir, now: NOW });
  const folders = {};
  for (const [fixture, o] of Object.entries(courses || {})) folders[fixture] = layoutCourse(dir, fixture, o);
  t.after(() => {
    const text = gas.logText();
    assert.ok(!/99\d{8,9}/.test(text), 'logs hold a student ID: ' + text);
    for (const n of STUDENT_NAMES) assert.ok(!text.includes(n), 'logs hold a student name: ' + n);
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return { gas, dir, folders };
}

// Every server function runs under the script lock: at least one acquire, all released.
function call(gas, name, ...args) {
  const n0 = gas.lockEvents.length;
  let reply;
  try {
    reply = gas.call(name, ...args);
  } finally {
    const ev = gas.lockEvents.slice(n0);
    assert.ok(ev.includes('acquire') || ev.includes('timeout'), name + ' did not take the script lock');
    assert.strictEqual(ev.filter((e) => e === 'acquire').length, ev.filter((e) => e === 'release').length,
      name + ' left the lock held');
  }
  if (reply && typeof reply === 'object') assert.ok(typeof reply.now === 'string', name + ' reply carries now');
  return reply;
}

const read = (folder, rel) => fs.readFileSync(path.join(folder, rel)).toString('utf8');
const journal = (folder) => read(folder, 'web_edits.jsonl').split('\n').filter((l) => l).map((l) => JSON.parse(l));
const pickCells = (xs) => xs.map((c) => ({ student_id: c.student_id, column: c.column, value: c.value }));

// ---- doGet and the course list ----
test('ac2_2 doGet shows Not available to another account', (t) => {
  const { gas } = setup(t, { [H.F1]: {} });
  gas.setUser('someone.else@example.test');
  const page = gas.doGet();
  assert.ok(page.content.includes('Not available'));
  for (const secret of ['ฟิสิกส์จำลอง', 'นายสมมติ', '9900000001', H.F1, 'teacher@example.test']) {
    assert.ok(!page.content.includes(secret), 'page shows ' + secret);
  }
  gas.setUser('teacher@example.test');
  const own = gas.doGet();
  assert.strictEqual(own.title, 'grade_web');
  assert.ok(own.meta.some((m) => m.name === 'viewport' && /width=device-width/.test(m.content)));
  assert.ok(gas.htmlRequests.includes('Index'));
});

test('ac2_1 listCourses lists two courses with unpulled and last saved', (t) => {
  const { gas } = setup(t, { [H.F1]: { journal: 'seven_lines.jsonl', archives: ['archive_pull_4.jsonl'] }, [H.F2]: {} });
  const r = call(gas, 'listCourses');
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.courses.length, 2);
  const c1 = r.courses.find((c) => c.folder === H.F1);
  assert.deepStrictEqual(c1, { folder: H.F1, available: true, course_id: 'MOCK', course_name: 'ฟิสิกส์จำลอง',
    term: '2027_S1', pushed_at: '2027-01-19T20:15:00+07:00', unpulled: 3, last_saved: '2027-01-20T09:45:00+07:00',
    older_push: false });
  const c2 = r.courses.find((c) => c.folder === H.F2);
  assert.strictEqual(c2.available, true);
  assert.strictEqual(c2.course_name, 'กลศาสตร์ทดลอง');
  assert.strictEqual(c2.unpulled, 0);
  assert.strictEqual(c2.last_saved, null);
});

test('older_push flags unpulled lines saved on an earlier push', (t) => {
  const { gas } = setup(t, { [H.F1]: { journal: 'undo_batches.jsonl' } });
  const c = call(gas, 'listCourses').courses[0];
  assert.strictEqual(c.older_push, true);
  assert.strictEqual(c.unpulled, 8);
});

test('ac2_3 course without course.json is unavailable, the other opens', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {}, [H.F2]: {} });
  fs.rmSync(path.join(folders[H.F2], 'course.json'));
  const r = call(gas, 'listCourses');
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.courses.find((c) => c.folder === H.F2), { folder: H.F2, available: false,
    reason: 'course.json is missing. Push the course again from the Mac: grader web-push' });
  assert.strictEqual(call(gas, 'loadCourse', H.F1).ok, true);
  const bad = call(gas, 'loadCourse', H.F2);
  assert.strictEqual(bad.ok, false);
  assert.strictEqual(bad.code, 'UNAVAILABLE');
});

test('ac2_4 loadCourse returns push time', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {}, [H.F2]: {} });
  const r = call(gas, 'loadCourse', H.F1);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.folder, H.F1);
  assert.strictEqual(r.push.pushed_at, '2027-01-19T20:15:00+07:00');
  assert.strictEqual(r.push.push_id, DEFAULT_PUSH);
  assert.strictEqual(r.course.course_name, 'ฟิสิกส์จำลอง');
  assert.strictEqual(r.roster, read(folders[H.F1], r.course.roster));
  assert.deepStrictEqual(Object.keys(r.files).sort(), r.course.files.slice().sort());
  for (const f of r.course.files) assert.strictEqual(r.files[f], read(folders[H.F1], f), f);
  assert.deepStrictEqual(r.journal, { unpulled: 0, last_saved: null, undo: null, undo_note: 'Nothing to undo' });
  const r2 = call(gas, 'loadCourse', H.F2);
  const hw2 = r2.files['data/9_กลศาสตร์ทดลอง_homework.csv'];
  assert.ok(hw2.startsWith('﻿Student ID,') && hw2.includes('\r\n'), 'BOM and CRLF reach the browser as they are');
});

test('loadCourse of an unknown course is NOT_FOUND', (t) => {
  const { gas } = setup(t, { [H.F1]: {} });
  const r = call(gas, 'loadCourse', '9_ไม่มี_grading');
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.code, 'NOT_FOUND');
});

// ---- availability ----
test('edge17 conflict copies make the course unavailable', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  fs.writeFileSync(path.join(folders[H.F1], 'web_edits (1).jsonl'), '');
  const c = call(gas, 'listCourses').courses[0];
  assert.strictEqual(c.available, false);
  assert.strictEqual(c.reason, 'Drive has duplicate files: web_edits (1).jsonl. See the README, "Duplicate files", then reload.');
  const before = read(folders[H.F1], HW);
  const s = call(gas, 'saveBatch', H.F1, [S81[0]]);
  assert.strictEqual(s.ok, false);
  assert.strictEqual(s.code, 'UNAVAILABLE');
  assert.strictEqual(read(folders[H.F1], HW), before, 'nothing written while unavailable');
});

test('edge29 damaged journal makes it unavailable', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: { journal: 'truncated.jsonl' } });
  const c = call(gas, 'listCourses').courses[0];
  assert.strictEqual(c.available, false);
  assert.strictEqual(c.reason, 'web_edits.jsonl has damaged lines: 3. See the README, "Damaged journal", then reload.');
  const jt = read(folders[H.F1], 'web_edits.jsonl');
  assert.strictEqual(call(gas, 'saveBatch', H.F1, [S81[0]]).code, 'UNAVAILABLE');
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), jt, 'invalid lines are never dropped');
});

test('edge19 missing journal is unavailable, not empty', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  fs.rmSync(path.join(folders[H.F1], 'web_edits.jsonl'));
  const c = call(gas, 'listCourses').courses[0];
  assert.strictEqual(c.available, false);
  assert.strictEqual(c.reason, 'web_edits.jsonl is missing. Push the course again from the Mac: grader web-push');
  assert.strictEqual(call(gas, 'loadCourse', H.F1).code, 'UNAVAILABLE');
  assert.ok(!fs.existsSync(path.join(folders[H.F1], 'web_edits.jsonl')), 'the web app never creates the journal');
});

// ---- saving ----
test('ac8_1 saveBatch writes CSVs and one batch of journal lines', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const hw0 = read(f, HW);
  const mid0 = read(f, MID);
  const r = call(gas, 'saveBatch', H.F1, S81);
  assert.strictEqual(r.ok, true);
  assert.match(r.batch, /^b-20270120-091502-[0-9a-f]{4}$/);
  assert.strictEqual(r.ts, NOW);
  assert.deepStrictEqual(pickCells(r.saved), pickCells(S81));
  assert.deepStrictEqual(r.already, []);
  assert.deepStrictEqual(r.conflicts, []);
  assert.strictEqual(r.files, 2);
  assert.strictEqual(r.journal.unpulled, 3);
  assert.strictEqual(r.journal.last_saved, NOW);
  assert.strictEqual(read(f, HW), hw0.replace('ทดสอบ,8,,,8', 'ทดสอบ,8,9,,8').replace('ใจดี,10,,7,17', 'ใจดี,10,8,7,17'));
  assert.strictEqual(read(f, MID), mid0.replace('ใจดี,18,18', 'ใจดี,20,18'));
  const lines = journal(f);
  assert.strictEqual(lines.length, 3);
  assert.ok(lines.every((l) => l.batch === r.batch && l.kind === 'cell' && l.ts === NOW && l.push === DEFAULT_PUSH));
  assert.deepStrictEqual(lines.map((l) => [l.seq, l.file, l.student_id, l.column, l.value, l.original]), [
    [0, HW, '9900000001', 'hw2', '9', ''], [1, HW, '9900000002', 'hw2', '8', ''],
    [2, MID, '9900000002', 'midterm_exam', '20', '18']]);
  assert.strictEqual(Object.keys(gas.props()).filter((k) => k.startsWith('pending')).length, 0);
});

test('ac8_2 second device conflict', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const a = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '7', original: '' }]);
  assert.strictEqual(a.saved.length, 1);
  gas.setNow('2027-01-20T09:16:00+07:00');
  const b = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]);
  assert.strictEqual(b.ok, true);
  assert.strictEqual(b.batch, null);
  assert.deepStrictEqual(b.saved, []);
  assert.deepStrictEqual(b.conflicts, [{ student_id: '9900000001', column: 'hw2', now: '7', reason: 'changed' }]);
  assert.strictEqual(H.Csv().parse(read(folders[H.F1], HW)).rows[0][3], '7');
  assert.strictEqual(journal(folders[H.F1]).length, 1);
  const again = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '7' }]);
  assert.strictEqual(again.saved.length, 1);
  assert.strictEqual(H.Csv().parse(read(folders[H.F1], HW)).rows[0][3], '9');
});

test('ac8_3 retry after a lost reply adds no journal line', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  call(gas, 'saveBatch', H.F1, S81);
  const jt = read(folders[H.F1], 'web_edits.jsonl');
  const hw = read(folders[H.F1], HW);
  gas.setNow('2027-01-20T09:17:00+07:00');
  const r = call(gas, 'saveBatch', H.F1, S81);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.batch, null);
  assert.deepStrictEqual(r.saved, []);
  assert.deepStrictEqual(pickCells(r.already), pickCells(S81));
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), jt);
  assert.strictEqual(read(folders[H.F1], HW), hw);
  assert.strictEqual(r.journal.unpulled, 3);
});

test('ac8_5 saves run under the lock one after another', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const n0 = gas.lockEvents.length;
  call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '7', original: '' }]);
  const b = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]);
  assert.deepStrictEqual(gas.lockEvents.slice(n0), ['acquire', 'release', 'acquire', 'release']);
  assert.strictEqual(b.conflicts[0].now, '7', 'the second save sees the first one');
  // BUSY when the lock times out: nothing written, edits stay with the client
  const hw = read(folders[H.F1], HW);
  const jt = read(folders[H.F1], 'web_edits.jsonl');
  gas.lockTimeout = true;
  const busy = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000002', column: 'hw2', value: '5', original: '' }]);
  assert.strictEqual(busy.ok, false);
  assert.strictEqual(busy.code, 'BUSY');
  assert.strictEqual(read(folders[H.F1], HW), hw);
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), jt);
});

test('ac8_6 untouched bytes, BOM and CRLF survive a save', (t) => {
  const { gas, folders } = setup(t, { [H.F2]: {} });
  const rel = 'data/9_กลศาสตร์ทดลอง_homework.csv';
  const before = fs.readFileSync(path.join(folders[H.F2], rel));
  const r = call(gas, 'saveBatch', H.F2, [{ student_id: '9900000104', column: 'hw3', value: '5', original: '' }]);
  assert.strictEqual(r.saved.length, 1);
  const after = fs.readFileSync(path.join(folders[H.F2], rel));
  const want = Buffer.from(before.toString('utf8').replace('9900000104,นางสาวคำ ลองดู,3,3.5,,6.5\r\n',
    '9900000104,นางสาวคำ ลองดู,3,3.5,5,6.5\r\n'), 'utf8');
  assert.ok(after.equals(want), 'only the target cell changed');
  assert.ok(after.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])));
});

test('edge35 crash between journal and CSV is rolled forward', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const hw0 = read(f, HW);
  gas.failOn('setContent', 2); // 1: the journal append, 2: the homework CSV
  assert.throws(() => gas.call('saveBatch', H.F1, [S81[0]]));
  assert.strictEqual(journal(f).length, 1, 'the journal line is written first');
  assert.strictEqual(read(f, HW), hw0, 'the CSV write failed');
  assert.ok(Object.keys(gas.props()).some((k) => k.startsWith('pending:')), 'pending marker left behind');
  gas.failOn('setContent', 0);
  const r = call(gas, 'loadCourse', H.F1); // the next locked call rolls the batch forward
  assert.strictEqual(r.ok, true);
  assert.strictEqual(read(f, HW), hw0.replace('ทดสอบ,8,,,8', 'ทดสอบ,8,9,,8'));
  assert.strictEqual(r.files[HW], read(f, HW));
  assert.ok(!Object.keys(gas.props()).some((k) => k.startsWith('pending:')));
  assert.strictEqual(journal(f).length, 1);
});

test('edge35 failed journal append leaves nothing behind', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const hw0 = read(f, HW);
  gas.failOn('setContent', 1);
  assert.throws(() => gas.call('saveBatch', H.F1, [S81[0]]));
  gas.failOn('setContent', 0);
  const r = call(gas, 'loadCourse', H.F1);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(read(f, HW), hw0);
  assert.strictEqual(read(f, 'web_edits.jsonl'), '');
  assert.ok(!Object.keys(gas.props()).some((k) => k.startsWith('pending:')));
  // a Retry then saves normally
  assert.strictEqual(call(gas, 'saveBatch', H.F1, [S81[0]]).saved.length, 1);
});

test('trim removes archived lines on the next call', (t) => {
  const seven = H.journalLines('seven_lines.jsonl');
  const bad = H.journalLines('truncated.jsonl')[2];
  const { gas, folders } = setup(t, { [H.F1]: { journal: 'seven_lines.jsonl' } });
  const f = folders[H.F1];
  fs.appendFileSync(path.join(f, 'web_edits.jsonl'), bad + '\n');
  assert.strictEqual(call(gas, 'listCourses').courses[0].available, false); // damaged, but still trimmed below
  fs.mkdirSync(path.join(f, 'archive'));
  fs.copyFileSync(path.join(H.JOURNALS, 'archive_pull_4.jsonl'), path.join(f, 'archive', 'web_edits_20270121-180000.jsonl'));
  call(gas, 'listCourses');
  const want = seven.slice(4).join('\n') + '\n' + bad + '\n';
  assert.strictEqual(read(f, 'web_edits.jsonl'), want);
  call(gas, 'listCourses');
  assert.strictEqual(read(f, 'web_edits.jsonl'), want, 'idempotent');
});

test('trim then counts only unarchived lines', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: { journal: 'seven_lines.jsonl', archives: ['archive_pull_4.jsonl'] } });
  const r = call(gas, 'loadCourse', H.F1);
  assert.strictEqual(r.journal.unpulled, 3);
  assert.strictEqual(journal(folders[H.F1]).length, 3);
});

test('ac6_5 attendance save writes P and A and 2 journal lines', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const r = call(gas, 'saveBatch', H.F1, [
    { student_id: '9900000001', column: '20 Jan 2027', value: 'P', original: '' },
    { student_id: '9900000002', column: '20 Jan 2027', value: 'A', original: '' }]);
  assert.strictEqual(r.saved.length, 2);
  assert.strictEqual(read(f, ATT), 'Student ID,Name,13 Jan 2027,20 Jan 2027,27 Jan 2027,total (3pts)\n' +
    '9900000001,นายสมมติ ทดสอบ,P,P,L,1.8\n9900000002,นางสาวตัวอย่าง ใจดี,P,A,A,1\n9900000003,นายทดลอง มีชื่อ,EA,,X,2\n');
  assert.deepStrictEqual(journal(f).map((l) => [l.column, l.value, l.file]), [['20 Jan 2027', 'P', ATT], ['20 Jan 2027', 'A', ATT]]);
});

test('ac6_7 nothing named .xlsx is read or written', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  fs.writeFileSync(path.join(folders[H.F1], 'data', '9_ฟิสิกส์จำลอง_attendance.xlsx'), 'not a workbook');
  call(gas, 'listCourses');
  call(gas, 'loadCourse', H.F1);
  call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: '20 Jan 2027', value: 'P', original: '' }]);
  const touched = gas.access.filter((a) => a.op !== 'list' && a.path.endsWith('.xlsx'));
  assert.deepStrictEqual(touched, []);
});

test('edge38 draft edits after a new push come back as not found or conflicts', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const r = call(gas, 'saveBatch', H.F1, [
    { student_id: '9900000099', column: 'hw2', value: '5', original: '' },
    { student_id: '9900000001', column: 'hw9', value: '4', original: '' },
    { student_id: '9900000001', column: 'hw1', value: '9', original: '7' },
    { student_id: '9900000002', column: 'hw3', value: '6', original: '7' }]);
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.conflicts.map((c) => [c.student_id, c.column, c.reason, c.now]), [
    ['9900000099', 'hw2', 'not found', null], ['9900000001', 'hw9', 'not found', null],
    ['9900000001', 'hw1', 'changed', '8']]);
  assert.deepStrictEqual(pickCells(r.saved), [{ student_id: '9900000002', column: 'hw3', value: '6' }]);
  assert.strictEqual(journal(folders[H.F1]).length, 1);
});

test('saveBatch refuses an invalid value', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const hw = read(folders[H.F1], HW);
  const r = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '8,5', original: '' }]);
  assert.deepStrictEqual(r.conflicts.map((c) => c.reason), ['invalid']);
  assert.strictEqual(read(folders[H.F1], HW), hw);
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), '');
});

// ---- undo ----
const A2 = [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' },
  { student_id: '9900000002', column: 'hw2', value: '8', original: '' }];

test('ac9_1 undoLastSave writes inverse lines that name the batch', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const hw0 = read(f, HW);
  const a = call(gas, 'saveBatch', H.F1, A2);
  const loaded = call(gas, 'loadCourse', H.F1);
  assert.deepStrictEqual(loaded.journal.undo, { batch: a.batch, ts: NOW, cells: 2, edits: A2 });
  assert.strictEqual(loaded.journal.undo_note, null);
  gas.setNow('2027-01-20T09:20:00+07:00');
  const u = call(gas, 'undoLastSave', H.F1, a.batch);
  assert.strictEqual(u.ok, true);
  assert.strictEqual(u.undoes, a.batch);
  assert.notStrictEqual(u.batch, a.batch);
  assert.strictEqual(u.saved.length, 2);
  assert.strictEqual(read(f, HW), hw0);
  const lines = journal(f).slice(2);
  assert.strictEqual(lines.length, 2);
  assert.ok(lines.every((l) => l.undoes === a.batch && l.batch === u.batch));
  assert.deepStrictEqual(lines.map((l) => [l.student_id, l.value, l.original]), [['9900000001', '', '9'], ['9900000002', '', '8']]);
  assert.strictEqual(u.journal.unpulled, 4);
});

test('ac9_2 changed cell kept as conflict', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const a = call(gas, 'saveBatch', H.F1, A2);
  // the cell changes on Drive without a new save (an undo can't target anything newer)
  fs.writeFileSync(path.join(f, HW), read(f, HW).replace('ใจดี,10,8,7,17', 'ใจดี,10,7,7,17'));
  const u = call(gas, 'undoLastSave', H.F1, a.batch);
  assert.strictEqual(u.ok, true);
  assert.deepStrictEqual(pickCells(u.saved), [{ student_id: '9900000001', column: 'hw2', value: '' }]);
  assert.deepStrictEqual(u.conflicts, [{ student_id: '9900000002', column: 'hw2', now: '7', reason: 'changed' }]);
  const rows = H.Csv().parse(read(f, HW)).rows;
  assert.deepStrictEqual([rows[0][3], rows[1][3]], ['', '7']);
});

test('ac9_3 unavailable after pull', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const a = call(gas, 'saveBatch', H.F1, A2);
  const lines = read(f, 'web_edits.jsonl');
  fs.mkdirSync(path.join(f, 'archive'));
  fs.writeFileSync(path.join(f, 'archive', 'web_edits_20270121-180000.jsonl'),
    JSON.stringify({ kind: 'pull', ts: '2027-01-21T18:00:00+07:00', tool: 'grader web-pull', mac_folder: H.F1,
      push: DEFAULT_PUSH, lines: 2 }) + '\n' + lines);
  const loaded = call(gas, 'loadCourse', H.F1);
  assert.strictEqual(loaded.journal.undo, null);
  assert.strictEqual(loaded.journal.undo_note, NOTE_PULLED);
  assert.strictEqual(loaded.journal.unpulled, 0);
  const hw = read(f, HW);
  const u = call(gas, 'undoLastSave', H.F1, a.batch);
  assert.strictEqual(u.ok, false);
  assert.strictEqual(u.code, 'UNDO_UNAVAILABLE');
  assert.strictEqual(u.message, NOTE_PULLED);
  assert.strictEqual(read(f, HW), hw);
});

test('ac9_5 two presses undo B then A', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const hw0 = read(f, HW);
  gas.setNow('2027-01-20T09:00:00+07:00');
  const a = call(gas, 'saveBatch', H.F1, A2);
  gas.setNow('2027-01-20T09:15:00+07:00');
  const b = call(gas, 'saveBatch', H.F1, [{ student_id: '9900000003', column: 'hw3', value: '6', original: '5' }]);
  gas.setNow('2027-01-20T09:20:00+07:00');
  assert.strictEqual(call(gas, 'loadCourse', H.F1).journal.undo.batch, b.batch);
  assert.strictEqual(call(gas, 'undoLastSave', H.F1, b.batch).ok, true);
  gas.setNow('2027-01-20T09:21:00+07:00');
  assert.strictEqual(call(gas, 'loadCourse', H.F1).journal.undo.batch, a.batch);
  assert.strictEqual(call(gas, 'undoLastSave', H.F1, a.batch).ok, true);
  const last = call(gas, 'loadCourse', H.F1);
  assert.strictEqual(last.journal.undo, null);
  assert.strictEqual(last.journal.undo_note, 'Nothing to undo');
  assert.strictEqual(read(f, HW), hw0);
});

test('UNDO_CHANGED when another save came first', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const a = call(gas, 'saveBatch', H.F1, A2);
  gas.setNow('2027-01-20T09:16:00+07:00');
  call(gas, 'saveBatch', H.F1, [{ student_id: '9900000003', column: 'hw3', value: '6', original: '5' }]);
  const jt = read(folders[H.F1], 'web_edits.jsonl');
  const u = call(gas, 'undoLastSave', H.F1, a.batch);
  assert.strictEqual(u.ok, false);
  assert.strictEqual(u.code, 'UNDO_CHANGED');
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), jt);
});

// ---- config ----
const W0 = { attendance: 0.1, homework: 0.2, midterm: 0.3, final: 0.4 };
const W1 = { attendance: 0.1, homework: 0.25, midterm: 0.3, final: 0.35 };
const typed = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, String(v)]));

test('ac10_1 saveConfig rewrites course.json and appends one config line', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  const before = JSON.parse(read(f, 'course.json'));
  const r = call(gas, 'saveConfig', H.F1, 'weights', typed(W1), W0);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.warning, null);
  assert.match(r.batch, /^b-20270120-091502-[0-9a-f]{4}$/);
  assert.deepStrictEqual(r.course.weights, W1);
  const after = JSON.parse(read(f, 'course.json'));
  assert.deepStrictEqual(after, Object.assign({}, before, { weights: W1 }));
  const lines = journal(f);
  assert.strictEqual(lines.length, 1);
  assert.deepStrictEqual(lines[0], { batch: r.batch, seq: 0, ts: NOW, kind: 'config', push: DEFAULT_PUSH,
    part: 'weights', value: W1, original: W0 });
  assert.strictEqual(r.journal.unpulled, 1);
  assert.strictEqual(r.journal.undo, null, 'config batches are not offered for undo');
});

test('ac10_2 saveConfig warns on a sum other than 1 and still saves', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const r = call(gas, 'saveConfig', H.F1, 'weights', typed(Object.assign({}, W0, { homework: 0.25 })), W0);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.warning, 'weights sum to 1.05');
  assert.strictEqual(JSON.parse(read(folders[H.F1], 'course.json')).weights.homework, 0.25);
});

test('ac10_3 saveConfig refuses a value that is not a number', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const cj = read(folders[H.F1], 'course.json');
  const r = call(gas, 'saveConfig', H.F1, 'weights', typed(Object.assign({}, W0, { homework: '0.2x' })), W0);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.code, 'INVALID');
  assert.strictEqual(r.field, 'homework');
  assert.strictEqual(read(folders[H.F1], 'course.json'), cj);
  assert.strictEqual(read(folders[H.F1], 'web_edits.jsonl'), '');
});

test('ac10_5 stale config refused, nothing written', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const f = folders[H.F1];
  assert.strictEqual(call(gas, 'saveConfig', H.F1, 'weights', typed(W1), W0).ok, true); // the other device
  const cj = read(f, 'course.json');
  const jt = read(f, 'web_edits.jsonl');
  gas.setNow('2027-01-20T09:40:00+07:00');
  const r = call(gas, 'saveConfig', H.F1, 'weights', typed(Object.assign({}, W0, { final: 0.45 })), W0);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.code, 'STALE_CONFIG');
  assert.deepStrictEqual(r.current, W1);
  assert.strictEqual(read(f, 'course.json'), cj);
  assert.strictEqual(read(f, 'web_edits.jsonl'), jt);
});

test('ac10_4 saveConfig keeps the stored letter order', (t) => {
  const { gas, folders } = setup(t, { [H.F1]: {} });
  const B0 = { A: 80, 'B+': 75, B: 70, 'C+': 65, C: 60, 'D+': 55, D: 50 };
  const r = call(gas, 'saveConfig', H.F1, 'grade_boundaries', typed(Object.assign({}, B0, { A: 78 })), B0);
  assert.strictEqual(r.ok, true);
  const gb = JSON.parse(read(folders[H.F1], 'course.json')).grade_boundaries;
  assert.deepStrictEqual(Object.keys(gb), Object.keys(B0));
  assert.strictEqual(gb.A, 78);
  const bad = call(gas, 'saveConfig', H.F1, 'grade_boundaries', typed(Object.assign({}, B0, { A: 78, 'B+': 81 })),
    Object.assign({}, B0, { A: 78 }));
  assert.deepStrictEqual([bad.ok, bad.code, bad.field], [false, 'INVALID', 'B+']);
});
