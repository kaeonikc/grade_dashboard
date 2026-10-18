'use strict';
// journal.js: parse, archived keys, unpulled, trim, conflict copies, undo target, line shapes, message formatters.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const H = require('./helpers.js');

const EXPECTED = JSON.parse(fs.readFileSync(path.join(H.JOURNALS, 'expected.json'), 'utf8'));
const ARCHIVE = H.journalText(EXPECTED.archive);
const keySet = (J, texts) => new Set(J.archivedKeys(texts));

test('journal contract matches expected.json', () => {
  const J = H.Journal();
  const keys = keySet(J, [ARCHIVE]);
  assert.strictEqual(keys.size, 4);
  for (const [name, e] of Object.entries(EXPECTED.journals)) {
    const parsed = J.parseJournal(H.journalText(name));
    assert.strictEqual(parsed.lines.length, e.valid, name + ' valid lines');
    assert.deepStrictEqual(parsed.bad, e.bad, name + ' bad lines');
    assert.strictEqual(parsed.lines.length + parsed.bad.length, e.lines, name + ' lines');
    const un = J.unpulled(parsed.lines, keys);
    assert.strictEqual(un.length, e.unpulled, name + ' unpulled');
    assert.deepStrictEqual(J.summary(un), { unpulled: e.unpulled, last_saved: e.last_saved }, name + ' summary');
  }
});

test('edge29 bad line numbers', () => {
  const J = H.Journal();
  assert.deepStrictEqual(J.parseJournal(H.journalText('truncated.jsonl')).bad, [3]);
  assert.deepStrictEqual(J.parseJournal('{"a":1}\nnot json\n\n[1,2]\n').bad, [2, 4]);
  assert.deepStrictEqual(J.parseJournal('').lines, []);
});

test('ac2_1 summary counts unpulled and last save', () => {
  const J = H.Journal();
  const lines = J.parseJournal(H.journalText('seven_lines.jsonl')).lines;
  const un = J.unpulled(lines, keySet(J, [ARCHIVE]));
  assert.deepStrictEqual(J.summary(un), { unpulled: 3, last_saved: '2027-01-20T09:45:00+07:00' });
  assert.deepStrictEqual(J.summary([]), { unpulled: 0, last_saved: null });
});

test('trim removes only archived keys', () => {
  const J = H.Journal();
  const seven = H.journalLines('seven_lines.jsonl');
  const bad = H.journalLines('truncated.jsonl')[2];
  const text = seven.slice(0, 3).join('\n') + '\n' + bad + '\n' + seven.slice(3).join('\n') + '\n';
  const keys = keySet(J, [ARCHIVE]);
  const out = J.trim(text, keys);
  assert.strictEqual(out, bad + '\n' + seven.slice(4).join('\n') + '\n');
  assert.strictEqual(J.trim(out, keys), out, 'idempotent');
  const plain = H.journalText('four_lines.jsonl');
  assert.strictEqual(J.trim(plain, keys), plain, 'nothing archived: identical');
});

test('edge17 conflictCopies', () => {
  const J = H.Journal();
  const expected = ['course.json', 'push.json', 'web_edits.jsonl', '9_ฟิสิกส์จำลอง_homework.csv',
    '9_ฟิสิกส์จำลอง_midterm.csv'];
  assert.deepStrictEqual(J.conflictCopies(expected, expected), []);
  assert.deepStrictEqual(J.conflictCopies(expected.concat(['web_edits (1).jsonl']), expected), ['web_edits (1).jsonl']);
  assert.deepStrictEqual(J.conflictCopies(expected.concat(['9_ฟิสิกส์จำลอง_homework (1).csv']), expected),
    ['9_ฟิสิกส์จำลอง_homework (1).csv']);
  assert.deepStrictEqual(J.conflictCopies(expected.concat(['course.json']), expected), ['course.json']);
  assert.deepStrictEqual(J.conflictCopies(expected.concat(['notes (1).txt']), expected), []);
});

const A = 'b-20270120-090000-a0a0';
const B = 'b-20270120-091500-b0b0';

test('ac9_5 undoTarget newest first', () => {
  const J = H.Journal();
  const lines = J.parseJournal(H.journalText('undo_batches.jsonl')).lines;
  // B is undone, the config batch and the older-push save are never offered, undo batches neither
  const t = J.undoTarget(lines, H.PUSH);
  assert.deepStrictEqual(t, {
    batch: A, ts: '2027-01-20T09:00:00+07:00', cells: 2,
    edits: [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' },
      { student_id: '9900000002', column: 'hw2', value: '8', original: '' }],
  });
  // without B's undo, B (newer) is the target
  assert.strictEqual(J.undoTarget(lines.filter((l) => !l.undoes), H.PUSH).batch, B);
  // once A is undone too, nothing is left for this push
  const undoA = lines.filter((l) => l.batch === A).map((l, i) => ({
    batch: 'b-20270120-094000-e0e0', seq: i, ts: '2027-01-20T09:40:00+07:00', kind: 'cell', push: H.PUSH,
    file: l.file, student_id: l.student_id, column: l.column, value: l.original, original: l.value, undoes: A,
  }));
  assert.strictEqual(J.undoTarget(lines.concat(undoA), H.PUSH), null);
  // the undo dialog lists at most 10 edits, cells counts all
  const big = [];
  for (let i = 0; i < 14; i++) {
    big.push({ batch: 'b-20270120-100000-1111', seq: i, ts: '2027-01-20T10:00:00+07:00', kind: 'cell', push: H.PUSH,
      file: 'data/x.csv', student_id: '99000000' + String(10 + i), column: 'hw1', value: '1', original: '' });
  }
  const tb = J.undoTarget(big, H.PUSH);
  assert.strictEqual(tb.cells, 14);
  assert.strictEqual(tb.edits.length, 10);
  assert.strictEqual(tb.edits[9].student_id, '9900000019');
});

test('ac9_3 undoTarget none after pull', () => {
  const J = H.Journal();
  const lines = J.parseJournal(H.journalText('four_lines.jsonl')).lines;
  const archive = '{"kind":"pull"}\n' + H.journalLines('four_lines.jsonl').join('\n') + '\n';
  const un = J.unpulled(lines, keySet(J, [archive]));
  assert.strictEqual(un.length, 0);
  assert.strictEqual(J.undoTarget(un, H.PUSH), null);
});

test('cellLines and configLine shape', () => {
  const J = H.Journal();
  const meta = { batch: 'b-20270120-091502-f00d', ts: '2027-01-20T09:15:02+07:00', push: H.PUSH };
  const lines = J.cellLines(meta, [
    { student_id: '9900000001', column: 'hw2', file: 'data/9_ฟิสิกส์จำลอง_homework.csv', value: '9', original: '' },
    { student_id: '9900000002', column: '20 Jan 2027', file: 'data/9_ฟิสิกส์จำลอง_attendance.csv', value: 'A', original: '' },
  ]);
  const obj = (l) => (typeof l === 'string' ? JSON.parse(l) : l);
  assert.deepStrictEqual(lines.map(obj), [
    { batch: meta.batch, seq: 0, ts: meta.ts, kind: 'cell', push: H.PUSH, file: 'data/9_ฟิสิกส์จำลอง_homework.csv',
      student_id: '9900000001', column: 'hw2', value: '9', original: '' },
    { batch: meta.batch, seq: 1, ts: meta.ts, kind: 'cell', push: H.PUSH, file: 'data/9_ฟิสิกส์จำลอง_attendance.csv',
      student_id: '9900000002', column: '20 Jan 2027', value: 'A', original: '' },
  ]);
  const text = lines.map((l) => (typeof l === 'string' ? l : JSON.stringify(l))).join('\n');
  assert.ok(text.includes('ฟิสิกส์'), 'Thai stays readable (no \\u escapes)');
  assert.strictEqual(typeof obj(lines[0]).student_id, 'string');
  const undo = J.cellLines(Object.assign({ undoes: 'b-20270120-090000-a0a0' }, meta),
    [{ student_id: '9900000001', column: 'hw2', file: 'data/x.csv', value: '', original: '9' }]).map(obj);
  assert.strictEqual(undo[0].undoes, 'b-20270120-090000-a0a0');
  const w0 = { attendance: 0.1, homework: 0.2, midterm: 0.3, final: 0.4 };
  const w1 = { attendance: 0.1, homework: 0.25, midterm: 0.3, final: 0.35 };
  assert.deepStrictEqual(obj(J.configLine(meta, 'weights', w1, w0)), {
    batch: meta.batch, seq: 0, ts: meta.ts, kind: 'config', push: H.PUSH, part: 'weights', value: w1, original: w0,
  });
});

// ---- message formatters (Interface "Formats" and copy table) ----
const NOW = '2027-01-20T10:00:00+07:00';

test('fmt plural, fmtTime and fmtAgo', () => {
  const F = H.Journal().fmt;
  assert.strictEqual(F.plural(1, 'cell'), '1 cell');
  assert.strictEqual(F.plural(2, 'cell'), '2 cells');
  assert.strictEqual(F.plural(0, 'edit'), '0 edits');
  assert.strictEqual(F.fmtTime('2027-01-20T09:15:02+07:00', NOW), '20 Jan 09:15');
  assert.strictEqual(F.fmtTime('2026-12-30T21:05:00+07:00', NOW), '30 Dec 2026 21:05');
  assert.strictEqual(F.fmtTime('2027-01-03T08:00:00+07:00', NOW), '3 Jan 08:00');
  assert.strictEqual(F.fmtAgo('2027-01-20T09:59:30+07:00', NOW), 'just now');
  assert.strictEqual(F.fmtAgo('2027-01-20T09:55:00+07:00', NOW), '5 min ago');
  assert.strictEqual(F.fmtAgo('2027-01-20T08:00:00+07:00', NOW), '2 h ago');
  assert.strictEqual(F.fmtAgo('2027-01-19T09:00:00+07:00', NOW), '1 day ago');
  assert.strictEqual(F.fmtAgo('2027-01-17T09:12:00+07:00', NOW), '3 days ago');
});

test('fmt journalLine and draftAge', () => {
  const F = H.Journal().fmt;
  assert.strictEqual(F.journalLine({ unpulled: 4, last_saved: '2027-01-20T09:15:00+07:00' }, NOW),
    '4 edits not pulled · last saved 20 Jan 09:15');
  assert.strictEqual(F.journalLine({ unpulled: 0, last_saved: null }, NOW), 'No edits waiting to be pulled');
  assert.strictEqual(F.draftAge('2027-01-20T09:12:40+07:00', NOW), 'from 20 Jan 09:12');
  assert.strictEqual(F.draftAge('2027-01-17T09:12:00+07:00', NOW), 'from 17 Jan 09:12, 3 days ago');
});

const COLUMNS = [
  { name: 'hw2', header: 'hw2 (10pts)', file: 'data/9_ฟิสิกส์จำลอง_homework.csv', category: 'homework' },
  { name: 'hw1', header: 'hw1 (10pts)', file: 'data/9_ฟิสิกส์จำลอง_homework.csv', category: 'homework' },
  { name: 'midterm_exam', header: 'midterm_exam (30pts)', file: 'data/9_ฟิสิกส์จำลอง_midterm.csv', category: 'midterm' },
];
const cellOf = (sid, column, value) => ({ student_id: sid, column, value });

test('fmt saveResult', () => {
  const F = H.Journal().fmt;
  const ok = { ok: true, batch: 'b-x', saved: [cellOf('9900000001', 'hw2', '9'), cellOf('9900000002', 'hw2', '8')],
    already: [cellOf('9900000002', 'midterm_exam', '20')], conflicts: [], push_changed: false };
  assert.strictEqual(F.saveResult(ok, COLUMNS), 'Saved 3 cells (2 files)');
  const retry = { ok: true, batch: null, saved: [], already: ok.saved.concat(ok.already), conflicts: [], push_changed: false };
  assert.strictEqual(F.saveResult(retry, COLUMNS), 'Saved 3 cells (2 files)');
  const one = { ok: true, saved: [cellOf('9900000001', 'hw2', '9')], already: [], conflicts: [], push_changed: false };
  assert.strictEqual(F.saveResult(one, COLUMNS), 'Saved 1 cell (1 file)');
  const conflict = { ok: true, batch: null, saved: [], already: [], push_changed: false,
    conflicts: [{ student_id: '9900000001', column: 'hw2', now: '7', reason: 'changed' }] };
  assert.strictEqual(F.saveResult(conflict, COLUMNS),
    'Saved 0 cells · 1 changed elsewhere, not saved: 9900000001 hw2 (now 7)');
  const many = { ok: true, saved: Array.from({ length: 12 }, (_, i) => cellOf('99000001' + String(10 + i), 'hw1', '1')),
    already: [], push_changed: false,
    conflicts: [['9900000001', 'hw2', '7'], ['9900000002', 'hw2', '8'], ['9900000003', 'hw1', '5'],
      ['9900000004', 'hw1', '6'], ['9900000005', 'hw1', '4']]
      .map(([s, c, n]) => ({ student_id: s, column: c, now: n, reason: 'changed' })) };
  assert.strictEqual(F.saveResult(many, COLUMNS), 'Saved 12 cells · 5 changed elsewhere, not saved: ' +
    '9900000001 hw2 (now 7), 9900000002 hw2 (now 8), 9900000003 hw1 (now 5) and 2 more');
  const notFound = { ok: true, saved: [], already: [], push_changed: false,
    conflicts: [{ student_id: '9900000099', column: 'hw2', now: null, reason: 'not found' },
      { student_id: '9900000001', column: 'hw9', now: null, reason: 'not found' }] };
  assert.ok(F.saveResult(notFound, COLUMNS).endsWith(
    ' · 2 not found (student or column not in this course): 9900000099 hw2, 9900000001 hw9'));
  const pushed = Object.assign({}, one, { push_changed: true });
  assert.ok(F.saveResult(pushed, COLUMNS).includes(
    'Some edits were made before the latest push; they were checked against the new data.'));
});

test('fmt undoTitle and undoResult', () => {
  const F = H.Journal().fmt;
  const target = { batch: 'b-20270120-091500-b0b0', ts: '2027-01-20T09:15:00+07:00', cells: 2,
    edits: [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' },
      { student_id: '9900000002', column: 'hw2', value: '8', original: '' }] };
  assert.strictEqual(F.undoTitle(target, NOW), 'Undo save of 20 Jan 09:15, 2 cells?');
  const all = { ok: true, batch: 'b-u', undoes: target.batch, saved: [cellOf('9900000001', 'hw2', ''),
    cellOf('9900000002', 'hw2', '')], already: [], conflicts: [] };
  assert.strictEqual(F.undoResult(all, target, NOW), 'Undid save of 20 Jan 09:15: 2 cells restored');
  const partial = { ok: true, batch: 'b-u', undoes: target.batch, saved: [cellOf('9900000001', 'hw2', '')], already: [],
    conflicts: [{ student_id: '9900000002', column: 'hw2', now: '7', reason: 'changed' }] };
  assert.strictEqual(F.undoResult(partial, target, NOW),
    'Undid 1 of 2 cells · 1 changed since, left as is: 9900000002 hw2 (now 7)');
  const none = { ok: true, batch: null, undoes: target.batch, saved: [], already: [],
    conflicts: [{ student_id: '9900000001', column: 'hw2', now: '6', reason: 'changed' },
      { student_id: '9900000002', column: 'hw2', now: '7', reason: 'changed' }] };
  assert.strictEqual(F.undoResult(none, target, NOW),
    'Nothing undone · 2 changed since, left as is: 9900000001 hw2 (now 6), 9900000002 hw2 (now 7)');
});
