'use strict';
// grades.js: golden parity with grade-tui (S12), S4 detail values, INTEGRATION.md tables, rounding and letters.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const H = require('./helpers.js');

const FIXTURE_NAMES = [H.F1, H.F2, H.F3, H.F4];

function checkAgainst(expected, course, rows, overlay, label) {
  const G = H.Grades();
  const got = G.computeGrades(course, rows, overlay || []);
  assert.deepStrictEqual(got.map((r) => r.student_id), expected.map((r) => r.student_id), label + ': order');
  const names = Object.fromEntries(rows.map((r) => [r.student_id, r.name]));
  for (let i = 0; i < expected.length; i++) {
    const e = expected[i];
    const g = got[i];
    const who = label + ' ' + e.student_id;
    assert.strictEqual(names[e.student_id], e.name, who + ': name');
    assert.deepStrictEqual(Object.keys(g.pct).sort(), Object.keys(e.pct).sort(), who + ': categories');
    for (const cat of Object.keys(e.pct)) assert.strictEqual(g.pct[cat], e.pct[cat], who + ': pct.' + cat);
    assert.strictEqual(g.coursework_total, e.coursework_total, who + ': coursework_total');
    assert.strictEqual(g.final_score, e.final_score, who + ': final_score');
    assert.strictEqual(g.grade, e.grade, who + ': grade');
  }
}

for (const name of FIXTURE_NAMES) {
  test('ac12_1 golden parity ' + name, () => {
    const g = H.loadGolden(name);
    checkAgainst(g.expected, g.course, H.rowsOf(g.course, name), [], name);
  });
}

test('ac12_1 golden variants', () => {
  const vs = H.variants();
  assert.ok(vs.length >= 4);
  for (const v of vs) {
    const g = H.loadGolden(v.fixture);
    const gv = g.variants.find((x) => x.name === v.name);
    assert.ok(gv, 'golden has variant ' + v.name);
    const course = H.withVariant(g.course, v);
    const overlay = (v.edits || []).map((e) => ({ student_id: e.student_id, column: e.column, value: e.value }));
    checkAgainst(gv.expected, course, H.rowsOf(g.course, v.fixture), overlay, v.name);
  }
});

const S41 = [
  { student_id: '9900000001', column: 'hw2', value: '9' },
  { student_id: '9900000001', column: '20 Jan 2027', value: 'P' },
];

function f1Student(overlay, sid) {
  const course = H.courseOf(H.F1);
  return H.Grades().computeGrades(course, H.rowsOf(course), overlay).find((r) => r.student_id === sid);
}

test('ac4_1 detail values for 9900000001', () => {
  const s = f1Student(S41, '9900000001');
  assert.strictEqual(s.pct.attendance, 9.33);
  assert.strictEqual(s.pct.homework, 17);
  assert.strictEqual(s.coursework_total, 27);
  assert.strictEqual(s.pct.midterm, 21);
  assert.strictEqual(s.pct.final, 0);
  assert.strictEqual(s.final_score, 48);
  assert.strictEqual(s.grade, 'F');
  assert.strictEqual(s.dropped, 'hw3');
});

test('ac4_2 typed 28 shows 76 B+', () => {
  const s = f1Student(S41.concat([{ student_id: '9900000001', column: 'final_exam', value: '28' }]), '9900000001');
  assert.strictEqual(s.pct.final, 28);
  assert.strictEqual(s.final_score, 76);
  assert.strictEqual(s.grade, 'B+');
});

test('ac4_3 ขส and abs count 0', () => {
  const G = H.Grades();
  assert.deepStrictEqual(G.classify('ขส'), ['absent', null]);
  assert.deepStrictEqual(G.classify('abs'), ['invalid', 'abs']);
  // 9900000003 in F1: hw1 'abs', midterm 'ขส' -> homework 5 of 20 after the drop, midterm 0
  const s = f1Student([], '9900000003');
  assert.strictEqual(s.pct.midterm, 0);
  assert.strictEqual(s.pct.homework, 5);
  // replacing abs by 0 changes nothing: both count 0
  const s0 = f1Student([{ student_id: '9900000003', column: 'hw1', value: '0' }], '9900000003');
  assert.deepStrictEqual(s0.pct, s.pct);
});

// ---- INTEGRATION.md tables, parsed at test time ----
const INTEGRATION = fs.readFileSync(path.join(H.WEB, '..', 'INTEGRATION.md'), 'utf8').split('\n');

function tableAfter(headerRe) {
  const i = INTEGRATION.findIndex((l) => headerRe.test(l));
  assert.ok(i >= 0, 'table header found: ' + headerRe);
  const rows = [];
  for (let j = i + 2; j < INTEGRATION.length && INTEGRATION[j].trim().startsWith('|'); j++) {
    rows.push(INTEGRATION[j].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()));
  }
  return rows;
}

function quoted(cell) { return [...cell.matchAll(/`([^`]*)`/g)].map((m) => m[1]); }

test('ac12_3 classify passes INTEGRATION cell table', () => {
  const G = H.Grades();
  const rows = tableAfter(/^\|\s*input\s*\|\s*kind\s*\|/);
  assert.ok(rows.length >= 5, 'cell table has >= 5 rows');
  let checked = 0;
  for (const [input, kind] of rows) {
    const [k, n] = kind.split(/\s+/);
    for (const text of quoted(input)) {
      let want;
      if (k === 'num') want = ['num', Number(n)];
      else if (k === 'invalid') want = ['invalid', text.trim()];
      else want = [k, null];
      assert.deepStrictEqual(G.classify(text), want, JSON.stringify(text));
      checked++;
    }
  }
  assert.ok(checked >= 10);
});

test('ac12_3 total rule table', () => {
  const G = H.Grades();
  const rows = tableAfter(/^\|\s*a\s*\|\s*b\s*\|\s*total\s*\|/);
  assert.ok(rows.length >= 5, 'total table has >= 5 rows');
  const val = (cell) => (cell === '(empty)' ? '' : quoted(cell)[0]);
  for (const [a, b, total] of rows) {
    const sum = [val(a), val(b)].reduce((s, t) => {
      const c = G.classify(t);
      return s + (c[0] === 'num' ? c[1] : 0);
    }, 0);
    assert.strictEqual(sum, Number(val(total)), a + ' + ' + b);
  }
});

test('dropped is the pandas idxmin choice', () => {
  const G = H.Grades();
  const drops = (fixture) => {
    const c = H.courseOf(fixture);
    return Object.fromEntries(G.computeGrades(c, H.rowsOf(c, fixture), []).map((r) => [r.student_id, r.dropped]));
  };
  const d1 = drops(H.F1);
  assert.strictEqual(d1['9900000001'], 'hw2'); // 8, blank, blank: first of the tied minimums
  assert.strictEqual(d1['9900000002'], 'hw2'); // 10, blank, 7
  assert.strictEqual(d1['9900000003'], 'hw1'); // abs (0), blank (0), 5
  const d3 = drops(H.F3);
  assert.strictEqual(d3['9900000201'], 'hw1'); // ratios 0.8, 0.8, 1.0
  assert.strictEqual(d3['9900000202'], 'hw1'); // ratios 0.5, 0.5, 1.0
  assert.strictEqual(d3['9900000203'], 'hw1'); // all blank
  assert.strictEqual(d3['9900000204'], 'hw3'); // unique lowest
  const d4 = drops(H.F4);
  assert.ok(Object.values(d4).every((x) => x === null), 'single homework column: rule does not apply');
  const d2 = drops(H.F2);
  assert.ok(Object.values(d2).every((x) => x === null), 'rule off');
});

test('round2 is numpy rint', () => {
  const G = H.Grades();
  assert.strictEqual(G.round2(0.625), 0.62);
  assert.strictEqual(G.round2(0.125), 0.12);
  assert.strictEqual(G.round2(2.675), 2.68); // 2.675*100 == 267.5 exactly; np.round and pandas give 2.68
  assert.strictEqual(G.round2(0.875), 0.88);
  assert.strictEqual(G.round2(9.333333333333334), 9.33);
  assert.strictEqual(G.round2(7.000000000000001), 7);
});

test('letterGrade uses sorted thresholds', () => {
  const G = H.Grades();
  const b = { A: 80, 'B+': 75, B: 70, 'C+': 65, C: 60, 'D+': 55, D: 50 };
  assert.strictEqual(G.letterGrade(80, b), 'A');
  assert.strictEqual(G.letterGrade(79, b), 'B+');
  assert.strictEqual(G.letterGrade(49, b), 'F');
  assert.strictEqual(G.letterGrade(50, b), 'D');
  const unordered = { D: 50, A: 80, C: 60, B: 70 };
  assert.strictEqual(G.letterGrade(72, unordered), 'B');
  assert.strictEqual(G.letterGrade(85, unordered), 'A');
});

// SPEC_grade_order.md: scale order, intervals, distribution and colour classes.
const B_SCALE = ['A', 'B+', 'B', 'C+', 'C', 'D+', 'D'];
const B_DEFAULT = { A: 80, 'B+': 75, B: 70, 'C+': 65, C: 60, 'D+': 55, D: 50 };
const reorder = (o, keys) => Object.fromEntries(keys.map((k) => [k, o[k]]));

test('gradeOrder ignores key order', () => {
  const G = H.Grades();
  const seen = reorder(B_DEFAULT, ['A', 'B', 'C', 'D', 'D+', 'C+', 'B+']); // the order the phone showed
  assert.deepStrictEqual(G.gradeOrder(seen), B_SCALE);
  assert.deepStrictEqual(G.gradeOrder(reorder(B_DEFAULT, Object.keys(B_DEFAULT).sort())), B_SCALE);
  assert.deepStrictEqual(G.gradeOrder(B_DEFAULT), B_SCALE);
  assert.deepStrictEqual(G.gradeOrder({ A: 80 }), ['A']);
  assert.deepStrictEqual(G.gradeOrder({}), []);
});

test('gradeOrder places unknown letters by saved value', () => {
  const G = H.Grades();
  assert.deepStrictEqual(G.gradeOrder(Object.assign({ 'A+': 85 }, B_DEFAULT)), ['A+'].concat(B_SCALE));
  assert.deepStrictEqual(G.gradeOrder(Object.assign({ E: 0 }, B_DEFAULT)), B_SCALE.concat('E'));
  assert.deepStrictEqual(G.gradeOrder({ D: 50, X: 72, A: 80, B: 70 }), ['A', 'X', 'B', 'D']);
  assert.deepStrictEqual(G.gradeOrder({ Z: 60, Y: 60, A: 80 }), ['A', 'Y', 'Z'], 'ties by key text');
});

test('gradeRanges are half-open intervals', () => {
  const G = H.Grades();
  const text = (b) => G.gradeRanges(G.gradeOrder(b), b).map((r) => r.letter + ' ' + r.text);
  assert.deepStrictEqual(text(B_DEFAULT), ['A X ≥ 80', 'B+ 75 ≤ X < 80', 'B 70 ≤ X < 75', 'C+ 65 ≤ X < 70',
    'C 60 ≤ X < 65', 'D+ 55 ≤ X < 60', 'D 50 ≤ X < 55', 'F X < 50']);
  const half = text(Object.assign({}, B_DEFAULT, { 'B+': 74.5 }));
  assert.strictEqual(half[1], 'B+ 74.5 ≤ X < 80');
  assert.strictEqual(half[2], 'B 70 ≤ X < 74.5');
  assert.deepStrictEqual(text({ A: 80 }), ['A X ≥ 80', 'F X < 80']);
});

test('letterGrade agrees with the intervals at their edges', () => {
  const G = H.Grades();
  const cases = [[69.9, 'C+'], [70, 'B'], [70.1, 'B'], [74.5, 'B'], [74.99, 'B'], [75, 'B+'], [80, 'A'], [49.9, 'F']];
  for (const [x, g] of cases) assert.strictEqual(G.letterGrade(x, B_DEFAULT), g, String(x));
});

test('distribution counts every row in scale order then F', () => {
  const G = H.Grades();
  for (const name of [H.F1, H.F2, H.F3, H.F4]) {
    const g = H.loadGolden(name);
    const order = G.gradeOrder(g.course.grade_boundaries);
    const rows = G.distribution(g.expected, order);
    assert.deepStrictEqual(rows.map((r) => r.letter), order.concat('F'), name);
    assert.strictEqual(rows.reduce((s, r) => s + r.count, 0), g.expected.length, name);
    for (const r of rows) {
      assert.strictEqual(r.count, g.expected.filter((e) => e.grade === r.letter).length, name + ' ' + r.letter);
      assert.strictEqual(r.pct, (r.count / g.expected.length) * 100);
    }
  }
  assert.deepStrictEqual(G.distribution([], ['A']), [{ letter: 'A', count: 0, pct: 0 }, { letter: 'F', count: 0, pct: 0 }]);
});

test('gradeClass mirrors grade_color_for', () => {
  const G = H.Grades();
  const want = { A: 'a', 'A+': 'a', 'B+': 'bp', B: 'b', 'C+': 'cp', C: 'c', 'D+': 'dp', D: 'd', F: 'f', E: 'f', '': 'f' };
  for (const k of Object.keys(want)) assert.strictEqual(G.gradeClass(k), want[k], k);
});

test('fillDefaultMax uses current weights', () => {
  const G = H.Grades();
  const c = H.courseOf(H.F3);
  const m = G.fillDefaultMax(c);
  assert.strictEqual(m.p1, 5);
  assert.strictEqual(m.p2, 5);
  assert.strictEqual(m.hw2, 2.5);
  assert.strictEqual(m.hw3, 2.5);
  assert.strictEqual(m.hw1, 15);
  assert.ok(!('x1' in m) || m.x1 === 100, 'weight 0: no derived max (100 at use)');
  const c2 = JSON.parse(JSON.stringify(c));
  c2.weights.project = 0.15;
  const m2 = G.fillDefaultMax(c2);
  assert.strictEqual(m2.p1, 7.5);
  assert.strictEqual(m2.p2, 7.5);
  assert.strictEqual(c.max_scores.p1, undefined, 'course.json is not modified');
});

test('ac2_5 computeGrades 300x80 under 1 s', () => {
  const G = H.Grades();
  const cats = ['attendance', 'homework', 'lab', 'quiz', 'midterm', 'final'];
  const per = { attendance: 15, homework: 20, lab: 25, quiz: 18, midterm: 1, final: 1 };
  const course = {
    format: 1, course_id: 'BIG', course_name: 'ใหญ่จำลอง', term: '2027_S1', folder: '9_ใหญ่_grading', prefix: '9_ใหญ่',
    category_order: cats,
    weights: { attendance: 0.1, homework: 0.2, lab: 0.15, quiz: 0.15, midterm: 0.2, final: 0.2 },
    grade_boundaries: { A: 80, 'B+': 75, B: 70, 'C+': 65, C: 60, 'D+': 55, D: 50 },
    rules: { drop_lowest_homework: true }, data_mapping: {}, total_pts: {}, max_scores: {},
    roster: 'course_info/9_ใหญ่_student_info.csv', files: [], columns: [],
  };
  const header = {};
  for (const cat of cats) {
    const file = 'data/9_ใหญ่_' + cat + '.csv';
    course.files.push(file);
    course.data_mapping[cat] = [];
    header[file] = ['Student ID', 'Name'];
    for (let i = 1; i <= per[cat]; i++) {
      const name = cat === 'attendance' ? 'a' + i : cat + i;
      course.data_mapping[cat].push(name);
      if (cat !== 'attendance') course.max_scores[name] = 10;
      course.columns.push({ name, header: cat === 'attendance' ? name : name + ' (10pts)', file, category: cat });
      header[file].push(cat === 'attendance' ? name : name + ' (10pts)');
    }
  }
  assert.strictEqual(course.columns.length, 80);
  let roster = 'Student ID,Name,Class Group\n';
  const files = {};
  for (const f of course.files) files[f] = header[f].join(',') + '\n';
  for (let s = 0; s < 300; s++) {
    const sid = '99' + String(10000000 + s);
    roster += sid + ',นักศึกษา ' + s + ',SEC1\n';
    for (const f of course.files) {
      const n = header[f].length - 2;
      const cells = [];
      for (let i = 0; i < n; i++) cells.push(f.endsWith('attendance.csv') ? 'PLAX'[(s + i) % 4] : String((s * 7 + i) % 11));
      files[f] += sid + ',นักศึกษา ' + s + ',' + cells.join(',') + '\n';
    }
  }
  const rows = G.mergeCourse(course, roster, files);
  const t0 = process.hrtime.bigint();
  const out = G.computeGrades(course, rows, []);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  assert.strictEqual(out.length, 300);
  assert.ok(ms < 1000, 'computeGrades took ' + ms + ' ms');
});
