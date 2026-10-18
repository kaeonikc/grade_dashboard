'use strict';
// save.planConfig + journal.configLine (S10.1-S10.5, edge 45).
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

const W0 = { attendance: 0.1, homework: 0.2, midterm: 0.3, final: 0.4 };
const B0 = { A: 80, 'B+': 75, B: 70, 'C+': 65, C: 60, 'D+': 55, D: 50 };
const typed = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, String(v)]));

test('ac10_2 sum warning', () => {
  const S = H.Save();
  const course = H.courseOf(H.F1);
  const r = S.planConfig(course, 'weights', typed(Object.assign({}, W0, { homework: 0.25 })), W0);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.warning, 'weights sum to 1.05');
  assert.strictEqual(r.course.weights.homework, 0.25);
});

test('ac10_1 new course.json changes only the part', () => {
  const S = H.Save();
  const J = H.Journal();
  const course = H.courseOf(H.F1);
  const before = JSON.stringify(course);
  const W1 = { attendance: 0.1, homework: 0.25, midterm: 0.3, final: 0.35 };
  const r = S.planConfig(course, 'weights', typed(W1), W0);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.warning, null, 'sum 1.0 (within float error) is not a warning');
  assert.deepStrictEqual(r.course.weights, W1);
  assert.deepStrictEqual(Object.assign({}, r.course, { weights: course.weights }), course);
  assert.strictEqual(JSON.stringify(course), before, 'input not modified');
  assert.deepStrictEqual(r.value, W1);
  const meta = { batch: 'b-20270120-093010-c4d0', ts: '2027-01-20T09:30:10+07:00', push: H.PUSH };
  const line = J.configLine(meta, 'weights', r.value, W0);
  const o = typeof line === 'string' ? JSON.parse(line) : line;
  assert.deepStrictEqual(o, Object.assign({}, meta, { seq: 0, kind: 'config', part: 'weights', value: W1, original: W0,
    batch: meta.batch, ts: meta.ts, push: H.PUSH }));
});

test('ac10_3 not a number names the field', () => {
  const S = H.Save();
  const course = H.courseOf(H.F1);
  for (const bad of ['0.2x', '0,25', '-1', '', 'abc']) {
    const r = S.planConfig(course, 'weights', typed(Object.assign({}, W0, { homework: bad })), W0);
    assert.deepStrictEqual({ ok: r.ok, code: r.code, field: r.field }, { ok: false, code: 'INVALID', field: 'homework' }, bad);
  }
  const rb = S.planConfig(course, 'grade_boundaries', typed(Object.assign({}, B0, { C: '6O' })), B0);
  assert.deepStrictEqual({ code: rb.code, field: rb.field }, { code: 'INVALID', field: 'C' });
});

test('ac10_4 boundaries strictly descending in stored order', () => {
  const S = H.Save();
  const course = H.courseOf(H.F1);
  const ok = S.planConfig(course, 'grade_boundaries', typed(Object.assign({}, B0, { A: 78 })), B0);
  assert.strictEqual(ok.ok, true);
  assert.deepStrictEqual(Object.keys(ok.course.grade_boundaries), Object.keys(B0));
  assert.strictEqual(ok.course.grade_boundaries.A, 78);
  const up = S.planConfig(course, 'grade_boundaries', typed(Object.assign({}, B0, { 'B+': 81 })), B0);
  assert.deepStrictEqual({ ok: up.ok, code: up.code, field: up.field }, { ok: false, code: 'INVALID', field: 'B+' });
  const eq = S.planConfig(course, 'grade_boundaries', typed(Object.assign({}, B0, { C: 65 })), B0);
  assert.deepStrictEqual({ code: eq.code, field: eq.field }, { code: 'INVALID', field: 'C' });
});

test('ac10_4 key set fixed', () => {
  const S = H.Save();
  const course = H.courseOf(H.F1);
  const extra = S.planConfig(course, 'grade_boundaries', typed(Object.assign({ 'A+': 90 }, B0)), B0);
  assert.strictEqual(extra.ok, false);
  assert.strictEqual(extra.code, 'INVALID');
  const missing = Object.assign({}, B0);
  delete missing.D;
  assert.strictEqual(S.planConfig(course, 'grade_boundaries', typed(missing), B0).code, 'INVALID');
  const cat = S.planConfig(course, 'weights', typed(Object.assign({}, W0, { lab: 0.1 })), W0);
  assert.strictEqual(cat.code, 'INVALID');
});

test('ac10_5 stale original refused', () => {
  const S = H.Save();
  const course = H.courseOf(H.F1);
  course.weights = { attendance: 0.1, homework: 0.25, midterm: 0.3, final: 0.35 }; // saved by the other device
  const r = S.planConfig(course, 'weights', typed(Object.assign({}, W0, { final: 0.45 })), W0);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.code, 'STALE_CONFIG');
  assert.deepStrictEqual(r.current, course.weights);
});
