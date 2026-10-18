'use strict';
// save.js: planSave (locate, conflict check, splice) and planUndo (S8.1-S8.3, S6.5, S9.1, S9.2, edges 6, 38).
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const H = require('./helpers.js');

const HW = 'data/9_ฟิสิกส์จำลอง_homework.csv';
const MID = 'data/9_ฟิสิกส์จำลอง_midterm.csv';
const ATT = 'data/9_ฟิสิกส์จำลอง_attendance.csv';
const S81 = [
  { student_id: '9900000001', column: 'hw2', value: '9', original: '' },
  { student_id: '9900000002', column: 'hw2', value: '8', original: '' },
  { student_id: '9900000002', column: 'midterm_exam', value: '20', original: '18' },
];
const META = { batch: 'b-20270120-091502-f00d', ts: '2027-01-20T09:15:02+07:00', push: H.PUSH };

function f1() {
  const course = H.courseOf(H.F1);
  return { course, files: H.textsOf(course).files };
}
const merged = (files, texts) => Object.assign({}, files, texts || {});
const cell = (text, sid, col) => {
  const doc = H.Csv().parse(text);
  const c = doc.header.findIndex((h) => h.trim() === col || h.trim().split(' (')[0] === col);
  return doc.rows.find((r) => r[0].trim() === sid)[c];
};

test('ac8_1 planSave three cells in two files', () => {
  const S = H.Save();
  const { course, files } = f1();
  const p = S.planSave(files, course, S81);
  assert.strictEqual(p.changes.length, 3);
  assert.deepStrictEqual(p.already, []);
  assert.deepStrictEqual(p.conflicts, []);
  assert.deepStrictEqual(Object.keys(p.texts).sort(), [HW, MID].sort());
  assert.deepStrictEqual(p.changes.map((c) => [c.student_id, c.column, c.file, c.value, c.original]), [
    ['9900000001', 'hw2', HW, '9', ''], ['9900000002', 'hw2', HW, '8', ''], ['9900000002', 'midterm_exam', MID, '20', '18']]);
  assert.strictEqual(p.texts[HW], files[HW]
    .replace('9900000001,นายสมมติ ทดสอบ,8,,,8', '9900000001,นายสมมติ ทดสอบ,8,9,,8')
    .replace('9900000002,นางสาวตัวอย่าง ใจดี,10,,7,17', '9900000002,นางสาวตัวอย่าง ใจดี,10,8,7,17'));
  assert.strictEqual(p.texts[MID], files[MID].replace('ใจดี,18,18', 'ใจดี,20,18'));
});

test('ac8_2 stale original is a conflict', () => {
  const S = H.Save();
  const { course, files } = f1();
  const drive = merged(files, { [HW]: files[HW].replace('ทดสอบ,8,,,8', 'ทดสอบ,8,7,,8') });
  const p = S.planSave(drive, course, [S81[0]]);
  assert.deepStrictEqual(p.changes, []);
  assert.deepStrictEqual(p.conflicts, [{ student_id: '9900000001', column: 'hw2', now: '7', reason: 'changed' }]);
  assert.ok(!p.texts[HW] || p.texts[HW] === drive[HW], 'nothing spliced for a conflict');
  // a second Save with the updated start value writes on purpose
  const p2 = S.planSave(drive, course, [Object.assign({}, S81[0], { original: '7' })]);
  assert.strictEqual(p2.changes.length, 1);
  assert.strictEqual(cell(p2.texts[HW], '9900000001', 'hw2'), '9');
});

test('ac8_3 retry is all already', () => {
  const S = H.Save();
  const { course, files } = f1();
  const p = S.planSave(files, course, S81);
  const p2 = S.planSave(merged(files, p.texts), course, S81);
  assert.deepStrictEqual(p2.changes, []);
  assert.strictEqual(p2.already.length, 3);
  assert.deepStrictEqual(p2.conflicts, []);
  for (const [f, t] of Object.entries(p2.texts || {})) assert.strictEqual(t, merged(files, p.texts)[f]);
  assert.deepStrictEqual(H.Journal().cellLines(META, p2.changes), []);
});

test('edge6 duplicate ID sets every row', () => {
  const S = H.Save();
  const file = 'data/dup.csv';
  const course = { columns: [{ name: 'hw1', header: 'hw1 (10pts)', file, category: 'homework' }], files: [file] };
  const text = H.readText(path.join(H.FIXTURES, 'csv', 'duplicate_ids.csv'));
  const p = S.planSave({ [file]: text }, course, [{ student_id: '9900000451', column: 'hw1', value: '9', original: '2' }]);
  assert.strictEqual(p.changes.length, 1);
  const rows = H.Csv().parse(p.texts[file]).rows;
  assert.deepStrictEqual(rows.map((r) => r[2]), ['9', '5', '9']);
  // padded IDs are compared trimmed
  const padded = H.readText(path.join(H.FIXTURES, 'csv', 'padded_ids.csv'));
  const p2 = S.planSave({ [file]: padded }, course, [{ student_id: '9900000441', column: 'hw1', value: '4', original: '3' }]);
  assert.strictEqual(p2.changes.length, 1);
  assert.strictEqual(p2.texts[file], padded.replace(' 9900000441 ,นายเว้น วรรค,3,3', ' 9900000441 ,นายเว้น วรรค,4,3'));
});

test('edge38 missing student or column is not found', () => {
  const S = H.Save();
  const { course, files } = f1();
  const p = S.planSave(files, course, [
    { student_id: '9900000099', column: 'hw2', value: '5', original: '' },
    { student_id: '9900000001', column: 'hw9', value: '4', original: '' },
    { student_id: '9900000001', column: 'total', value: '30', original: '8' },
  ]);
  assert.deepStrictEqual(p.changes, []);
  assert.deepStrictEqual(p.conflicts.map((c) => [c.student_id, c.column, c.reason]), [
    ['9900000099', 'hw2', 'not found'], ['9900000001', 'hw9', 'not found'], ['9900000001', 'total', 'not found']]);
});

test('invalid value is refused server-side', () => {
  const S = H.Save();
  const { course, files } = f1();
  const p = S.planSave(files, course, [
    { student_id: '9900000001', column: 'hw2', value: '8,5', original: '' },
    { student_id: '9900000002', column: 'hw2', value: '-1', original: '' },
    { student_id: '9900000003', column: 'hw2', value: 'abc', original: '' },
    { student_id: '9900000001', column: '20 Jan 2027', value: 'EA', original: '' },
  ]);
  assert.deepStrictEqual(p.changes, []);
  assert.ok(p.conflicts.every((c) => c.reason === 'invalid'), JSON.stringify(p.conflicts));
  assert.strictEqual(p.conflicts.length, 4);
  // canonical values are what gets written
  const q = S.planSave(files, course, [{ student_id: '9900000001', column: 'hw2', value: '08.50', original: '' }]);
  assert.strictEqual(q.changes[0].value, '8.5');
  assert.strictEqual(cell(q.texts[HW], '9900000001', 'hw2'), '8.5');
});

test('ac6_5 attendance P and A spliced', () => {
  const S = H.Save();
  const { course, files } = f1();
  const p = S.planSave(files, course, [
    { student_id: '9900000001', column: '20 Jan 2027', value: 'P', original: '' },
    { student_id: '9900000002', column: '20 Jan 2027', value: 'A', original: '' },
  ]);
  assert.strictEqual(p.changes.length, 2);
  assert.strictEqual(p.texts[ATT],
    'Student ID,Name,13 Jan 2027,20 Jan 2027,27 Jan 2027,total (3pts)\n' +
    '9900000001,นายสมมติ ทดสอบ,P,P,L,1.8\n' +
    '9900000002,นางสาวตัวอย่าง ใจดี,P,A,A,1\n' +
    '9900000003,นายทดลอง มีชื่อ,EA,,X,2\n');
});

test('ac9_1 planUndo inverts the batch', () => {
  const S = H.Save();
  const J = H.Journal();
  const { course, files } = f1();
  const lines = J.parseJournal(H.journalText('from_web.jsonl')).lines;
  const inv = S.planUndo(lines, META.batch);
  assert.deepStrictEqual(inv, [
    { student_id: '9900000001', column: 'hw2', value: '', original: '9' },
    { student_id: '9900000002', column: 'hw2', value: '', original: '8' },
    { student_id: '9900000002', column: 'midterm_exam', value: '18', original: '20' },
  ]);
  const saved = merged(files, S.planSave(files, course, S81).texts);
  const p = S.planSave(saved, course, inv);
  assert.strictEqual(p.changes.length, 3);
  assert.strictEqual(merged(saved, p.texts)[HW], files[HW]);
  assert.strictEqual(merged(saved, p.texts)[MID], files[MID]);
  const ul = J.cellLines(Object.assign({ undoes: META.batch }, META, { batch: 'b-20270120-093000-0b0b' }), p.changes)
    .map((l) => (typeof l === 'string' ? JSON.parse(l) : l));
  assert.ok(ul.length === 3 && ul.every((l) => l.undoes === META.batch));
});

test('ac9_2 planUndo skips a cell changed since', () => {
  const S = H.Save();
  const J = H.Journal();
  const { course, files } = f1();
  const saved = merged(files, S.planSave(files, course, S81).texts);
  saved[HW] = saved[HW].replace('ใจดี,10,8,7,17', 'ใจดี,10,7,7,17'); // changed after that save
  const inv = S.planUndo(J.parseJournal(H.journalText('from_web.jsonl')).lines, META.batch);
  const p = S.planSave(saved, course, inv);
  assert.strictEqual(p.changes.length, 2);
  assert.deepStrictEqual(p.conflicts, [{ student_id: '9900000002', column: 'hw2', now: '7', reason: 'changed' }]);
  assert.strictEqual(cell(p.texts[HW], '9900000001', 'hw2'), '');
  assert.strictEqual(cell(p.texts[HW], '9900000002', 'hw2'), '7');
});

test('from_web.jsonl is what save writes', () => {
  const S = H.Save();
  const J = H.Journal();
  const { course, files } = f1();
  const p = S.planSave(files, course, S81);
  const lines = J.cellLines(META, p.changes);
  const text = lines.map((l) => (typeof l === 'string' ? l : JSON.stringify(l))).join('\n') + '\n';
  assert.strictEqual(text, H.journalText('from_web.jsonl'));
});
