'use strict';
// grades.fillTargets and grades.sessionDate (S6.1, S6.6, S7.1-S7.5, edge 47).
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

function f1() {
  const course = H.courseOf(H.F1);
  return { course, rows: H.rowsOf(course) };
}
const ids = (targets) => targets.map((t) => t.student_id).sort();

test('ac7_1 only empty cells counts 2', () => {
  const G = H.Grades();
  const { rows } = f1();
  const overlay = [{ student_id: '9900000001', column: 'hw2', value: '9' }];
  const t = G.fillTargets(rows, overlay, 'hw2', '0', 'empty');
  assert.strictEqual(t.length, 2);
  assert.deepStrictEqual(ids(t), ['9900000002', '9900000003']);
  assert.ok(t.every((x) => x.value === '0'));
});

test('ac7_2 whole column counts 3', () => {
  const G = H.Grades();
  const { rows } = f1();
  const overlay = [{ student_id: '9900000001', column: 'hw2', value: '9' }];
  assert.strictEqual(G.fillTargets(rows, overlay, 'hw2', '10', 'whole').length, 3);
  // a cell already equal to the value is not counted (hw1: 8, 10, abs)
  assert.deepStrictEqual(ids(G.fillTargets(rows, [], 'hw1', '10', 'whole')), ['9900000001', '9900000003']);
  assert.deepStrictEqual(ids(G.fillTargets(rows, [], 'hw1', '10.0', 'whole')), ['9900000001', '9900000003']);
});

test('ac7_3 unsaved value counts as filled', () => {
  const G = H.Grades();
  const { rows } = f1();
  const overlay = [{ student_id: '9900000002', column: 'hw2', value: '7' }];
  assert.deepStrictEqual(ids(G.fillTargets(rows, overlay, 'hw2', '0', 'empty')), ['9900000001', '9900000003']);
  // an unsaved blank over a saved value counts as empty
  const cleared = [{ student_id: '9900000002', column: 'hw1', value: '' }];
  assert.deepStrictEqual(ids(G.fillTargets(rows, cleared, 'hw1', '5', 'empty')), ['9900000002']);
});

test('ac7_5 zero targets', () => {
  const G = H.Grades();
  const { rows } = f1();
  const full = ['9900000001', '9900000002', '9900000003'].map((s) => ({ student_id: s, column: 'hw2', value: '4' }));
  assert.deepStrictEqual(G.fillTargets(rows, full, 'hw2', '0', 'empty'), []);
  assert.deepStrictEqual(G.fillTargets(rows, full, 'hw2', '4', 'whole'), []);
});

test('ac7_4 fill value validated', () => {
  const G = H.Grades();
  assert.strictEqual(G.validateTyped('8,5').reason, 'comma');
  assert.strictEqual(G.validateTyped('-1').reason, 'negative');
  assert.strictEqual(G.validateTyped('abc').reason, 'other');
  assert.strictEqual(G.validateTyped('ขส').ok, true);
  // attendance: P (and Clear = '') fill a session column
  const { rows } = f1();
  assert.strictEqual(G.fillTargets(rows, [], '20 Jan 2027', 'P', 'whole').length, 3);
  assert.strictEqual(G.fillTargets(rows, [], '27 Jan 2027', '', 'whole').length, 3);
});

test('ac6_6 fill P then one A gives 3 unsaved', () => {
  const G = H.Grades();
  const { rows } = f1();
  const t = G.fillTargets(rows, [], '20 Jan 2027', 'P', 'whole');
  assert.strictEqual(t.length, 3);
  const overlay = new Map(t.map((x) => [x.student_id, { student_id: x.student_id, column: '20 Jan 2027', value: x.value }]));
  overlay.set('9900000002', { student_id: '9900000002', column: '20 Jan 2027', value: 'A' });
  const values = [...overlay.values()].map((e) => e.value).sort();
  assert.deepStrictEqual(values, ['A', 'P', 'P']);
  // EA is kept by "only empty cells" (13 Jan 2027: P, P, EA -> nothing empty)
  assert.deepStrictEqual(G.fillTargets(rows, [], '13 Jan 2027', 'P', 'empty'), []);
});

test('ac6_1 sessionDate and today\'s session', () => {
  const G = H.Grades();
  assert.strictEqual(G.sessionDate('20 Jan 2027'), '2027-01-20');
  assert.strictEqual(G.sessionDate(' 3 Feb 2027 '), '2027-02-03');
  assert.strictEqual(G.sessionDate('a1'), null);
  assert.strictEqual(G.sessionDate('total (3pts)'), null);
  const sessions = H.courseOf(H.F1).data_mapping.attendance;
  const today = (iso) => sessions.find((s) => G.sessionDate(s) === iso) || null;
  assert.strictEqual(today('2027-01-20'), '20 Jan 2027');
  assert.strictEqual(today('2027-01-21'), null);
});
