'use strict';
// grades.js attendance grid stats (SPEC_attendance_grid.md), over fixture F2: sessions 13, 20 and 27 Jan 2027.
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

function f2() {
  const G = H.Grades();
  const course = H.courseOf(H.F2);
  const rows = H.rowsOf(course);
  const sessions = course.columns.filter((c) => c.category === 'attendance');
  return { G, rows, sessions, text: (r, col) => r.cells[col] || '' };
}

const pick = (st) => ({ held: st.held, total: Math.round(st.total * 10) / 10, pct: st.pct, counts: st.counts,
  atRisk: st.atRisk });
const c = (P, L, A, X, blank) => ({ P, L, A, X, blank });

test('two sessions held on 2027-01-21', () => {
  const { G, rows, sessions, text } = f2();
  const out = G.attendanceStats(rows, sessions, text, '2027-01-21');
  assert.deepStrictEqual(out.sessions.map((s) => s.held), [true, true, false]);
  const want = {
    9900000101: { held: 2, total: 2, pct: 100, counts: c(2, 0, 0, 0, 0), atRisk: false },
    9900000104: { held: 2, total: 0.8, pct: 40, counts: c(0, 1, 1, 0, 0), atRisk: true },
    9900000105: { held: 2, total: 2, pct: 100, counts: c(0, 0, 0, 2, 0), atRisk: false },
    9900000106: { held: 2, total: 1, pct: 50, counts: c(1, 0, 1, 0, 0), atRisk: true },
    9900000107: { held: 2, total: 0, pct: 0, counts: c(0, 0, 2, 0, 0), atRisk: true },
    9900000108: { held: 2, total: 0, pct: 0, counts: c(0, 0, 0, 0, 2), atRisk: true },
  };
  for (const sid of Object.keys(want)) assert.deepStrictEqual(pick(out.students.get(sid)), want[sid], sid);
  const s13 = out.sessions[0];
  assert.deepStrictEqual(s13.counts, c(3, 1, 2, 1, 2));
  assert.strictEqual(s13.present, 5);
  assert.strictEqual(G.fmtAttTotal(out.students.get('9900000104')), '0.8 / 2 · 40%');
});

test('nothing held on 2027-01-12', () => {
  const { G, rows, sessions, text } = f2();
  const st = G.attendanceStats(rows, sessions, text, '2027-01-12').students.get('9900000104');
  assert.deepStrictEqual(pick(st), { held: 0, total: 0, pct: null, counts: c(0, 0, 0, 0, 0), atRisk: false });
  assert.strictEqual(G.fmtAttTotal(st), '—');
});

test('all held on 2027-02-01; an invalid code counts nowhere', () => {
  const { G, rows, sessions, text } = f2();
  const out = G.attendanceStats(rows, sessions, text, '2027-02-01');
  assert.deepStrictEqual(pick(out.students.get('9900000105')),
    { held: 3, total: 2, pct: (20 * 10) / 3, counts: c(0, 0, 0, 2, 0), atRisk: true });
  assert.deepStrictEqual(pick(out.students.get('9900000106')),
    { held: 3, total: 1.8, pct: 60, counts: c(1, 1, 1, 0, 0), atRisk: true });
  assert.strictEqual(out.sessions[2].present, 4, '27 Jan: P×3 + L; the invalid p is not present');
  assert.strictEqual(G.fmtAttTotal(out.students.get('9900000105')), '2.0 / 3 · 66%');
});

test('unsaved edits count', () => {
  const { G, rows, sessions, text } = f2();
  const edited = (r, col) => (r.student_id === '9900000107' && col === '20 Jan 2027' ? 'P' : text(r, col));
  const st = G.attendanceStats(rows, sessions, edited, '2027-01-21').students.get('9900000107');
  assert.deepStrictEqual(pick(st), { held: 2, total: 1, pct: 50, counts: c(1, 0, 1, 0, 0), atRisk: true });
});

test('undated sessions are held once any row has a code', () => {
  const G = H.Grades();
  const sessions = ['a1', 'a2', 'a3'].map((n) => ({ name: n, header: n }));
  const rows = [{ student_id: '1', cells: { a1: 'P', a2: '' } }, { student_id: '2', cells: { a1: 'L' } }];
  const out = G.attendanceStats(rows, sessions, (r, col) => r.cells[col] || '', '2026-10-19');
  assert.deepStrictEqual(out.sessions.map((s) => s.held), [true, false, false]);
  assert.strictEqual(out.students.get('2').pct, 80);
  assert.strictEqual(out.students.get('2').atRisk, false, 'exactly 80% is not at risk');
});

test('80% boundary and rounding down', () => {
  const G = H.Grades();
  const sessions = [1, 2, 3, 4, 5].map((d) => ({ name: 's' + d, header: d + ' Jan 2027' }));
  const row = (codes) => ({ student_id: codes, cells: Object.fromEntries(codes.split('').map((k, i) => ['s' + (i + 1),
    k === '-' ? '' : k])) });
  const out = G.attendanceStats([row('PPPPA'), row('PPPPL'), row('LLLLL')], sessions, (r, col) => r.cells[col] || '',
    '2027-01-31');
  assert.strictEqual(out.students.get('PPPPA').pct, 80);
  assert.strictEqual(out.students.get('PPPPA').atRisk, false);
  assert.strictEqual(out.students.get('LLLLL').pct, 80, '0.8 × 5 is exactly 80%, not 79.99…');
  assert.strictEqual(G.fmtAttTotal({ held: 3, total: 2.4, pct: 79.99 }), '2.4 / 3 · 79%');
  assert.strictEqual(G.fmtAttTotal(out.students.get('PPPPL')), '4.8 / 5 · 96%');
});

test('shortDate', () => {
  const G = H.Grades();
  assert.strictEqual(G.shortDate('16 Jun 2026'), '16/6');
  assert.strictEqual(G.shortDate('3 Feb 2027'), '3/2');
  assert.strictEqual(G.shortDate('a3'), 'a3');
});
