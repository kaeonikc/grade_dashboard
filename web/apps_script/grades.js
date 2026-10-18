// grades.js: grade-tui's grade math in JS (web/SPEC.md "Grade math in the browser"). One factory, no globals (ADR 004).
// Mirrors src/cells.py, src/data_loader.py (rows), tui_api._fill_default_max_scores and calculators.py step by step,
// in the same operation order, so every float rounds the same way. The golden tests are the authority.
// Csv = gwCsv() (mergeCourse parses the texts with it); node's require supplies it.
function gwGrades(Csv) {
  'use strict';

  const ABSENT = 'ขส';
  const CODE_VALUE = { P: 1.0, L: 0.8, X: 1.0, EA: 1.0, A: 0.0 };
  const SENTINELS = ['max score', 'max', 'full score', 'full'];
  // What Python's float() accepts (ASCII digits; inf/nan are invalid cells anyway).
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const FLOAT = /^[+-]?(\d(_?\d)*(\.(\d(_?\d)*)?)?|\.\d(_?\d)*)([eE][+-]?\d(_?\d)*)?$/;

  // cells.classify: ['num', number] | ['empty', null] | ['absent', null] | ['invalid', text].
  function classify(value) {
    const text = String(value == null ? '' : value).trim();
    if (text === '' || text.toLowerCase() === 'nan') return ['empty', null];
    if (text === ABSENT) return ['absent', null];
    const s = text.replace(/,/g, '');
    if (!FLOAT.test(s)) return ['invalid', text];
    const x = Number(s.replace(/_/g, ''));
    return Number.isFinite(x) ? ['num', x] : ['invalid', text];
  }

  function sameCell(a, b) {
    const x = classify(a);
    const y = classify(b);
    return x[0] === y[0] && x[1] === y[1];
  }

  // numpy round(x, 2) = rint(x * 100) / 100, half to even on the scaled double.
  function round2(x) {
    const y = x * 100;
    let r = Math.round(y);
    if (r - y === 0.5 && r % 2 !== 0) r -= 1;
    return r / 100;
  }

  // assign_letter_grade: the first boundary, highest threshold first, that the score reaches.
  function letterGrade(score, boundaries) {
    const sorted = Object.keys(boundaries).map((g) => [g, boundaries[g]]).sort((a, b) => b[1] - a[1]);
    for (const [g, t] of sorted) if (score >= t) return g;
    return 'F';
  }

  // Rows in Raw Details order: every Student ID of the roster and the pushed files (blank IDs and a legacy
  // sentinel first row skipped), sorted as text. Name = the first non-empty one, roster first.
  // cells holds the counted columns' texts as written; a student without a row in a file has none.
  function mergeCourse(course, rosterText, files) {
    const byId = new Map();
    const row = (sid) => {
      if (!byId.has(sid)) byId.set(sid, { student_id: sid, name: '', cells: Object.create(null) });
      return byId.get(sid);
    };
    const add = (text, cols, sentinelRow) => {
      const doc = Csv.parse(text);
      const header = doc.header.map((h) => h.trim());
      const iId = header.indexOf('Student ID');
      if (iId < 0) return;
      const iName = header.indexOf('Name');
      const idx = cols.map((c) => [c.name, header.indexOf(c.header.trim())]).filter((p) => p[1] >= 0);
      let first = true;
      for (const r of doc.rows) {
        const sid = (r[iId] || '').trim();
        if (sid === '') continue;
        const sentinel = sentinelRow && first && SENTINELS.includes(sid.toLowerCase());
        first = false;
        if (sentinel) continue;
        const target = row(sid);
        const name = iName >= 0 ? (r[iName] || '').trim() : '';
        if (!target.name && name !== 'nan') target.name = name;
        for (const [n, i] of idx) if (!(n in target.cells)) target.cells[n] = r[i] || '';
      }
    };
    add(rosterText, [], false);
    for (const f of course.files) add(files[f], course.columns.filter((c) => c.file === f), true);
    const order = (a, b) => (a.student_id < b.student_id ? -1 : a.student_id > b.student_id ? 1 : 0);
    return Array.from(byId.values()).sort(order);
  }

  // _fill_default_max_scores with the course's current weights; returns a new map (course.json is not changed).
  function fillDefaultMax(course) {
    const max = Object.assign({}, course.max_scores);
    for (const cat of Object.keys(course.data_mapping)) {
      const cols = course.data_mapping[cat];
      if (cat === 'attendance') continue;
      const weight = Number(course.weights[cat] || 0);
      if (weight <= 0 || !cols || !cols.length) continue;
      const target = weight * 100.0;
      let specified = 0;
      for (const c of cols) if (has(max, c)) specified += max[c];
      const unspecified = cols.filter((c) => !has(max, c));
      if (unspecified.length) {
        const per = Math.max(target - specified, 0.0) / unspecified.length;
        for (const c of unspecified) max[c] = per;
      }
    }
    return max;
  }

  const sum = (xs) => xs.reduce((s, x) => s + x, 0);

  // calculate_final_grades + get_course_data's summary, one object per row (Raw Details order).
  // overlay = unsaved edits [{student_id, column, value}], applied over the saved texts.
  function computeGrades(course, rows, overlay) {
    const max = fillDefaultMax(course);
    const present = new Set(course.columns.map((c) => c.name));
    const edits = new Map();
    for (const e of overlay || []) edits.set(e.student_id + '\u0000' + e.column, e.value);
    const cats = course.category_order.filter((c) => has(course.weights, c));
    const dropRule = !!(course.rules && course.rules.drop_lowest_homework);
    return rows.map((r) => {
      const text = (col) => {
        const k = r.student_id + '\u0000' + col;
        return edits.has(k) ? edits.get(k) : (r.cells[col] || '');
      };
      const score = (col) => {
        const c = classify(text(col));
        return c[0] === 'num' ? c[1] : 0;
      };
      const pct = {};
      let ct = null;
      let dropped = null;
      for (const cat of cats) {
        const weight = course.weights[cat];
        const valid = (course.data_mapping[cat] || []).filter((c) => present.has(c));
        if (!valid.length) {
          pct[cat] = 0;
          continue;
        }
        const colMax = (c) => (has(max, c) ? max[c] : 100.0);
        let catSum;
        let possible;
        if (cat === 'attendance') {
          catSum = sum(valid.map((c) => {
            const code = text(c).trim();
            return has(CODE_VALUE, code) ? CODE_VALUE[code] : 0.0;
          }));
          possible = valid.length;
        } else if (cat === 'homework' && dropRule && valid.length > 1) {
          let drop = null;
          let low = NaN;
          for (const c of valid) {
            const ratio = score(c) / colMax(c);
            if (!Number.isNaN(ratio) && (drop === null || ratio < low)) { drop = c; low = ratio; }
          }
          dropped = drop;
          const kept = valid.filter((c) => c !== drop);
          catSum = sum(kept.map(score));
          possible = sum(kept.map(colMax));
        } else {
          catSum = sum(valid.map(score));
          possible = sum(Array.from(new Set(valid)).map(colMax));
        }
        const tp = course.total_pts ? course.total_pts[cat] : undefined;
        if (tp != null) possible = Math.max(possible, tp);
        const weighted = (possible > 0 ? catSum / possible : 0.0) * 100 * weight;
        pct[cat] = round2(weighted);
        if (cat.toLowerCase() !== 'midterm' && cat.toLowerCase() !== 'final') ct = (ct === null ? 0.0 : ct) + weighted;
      }
      if (has(pct, 'midterm')) pct.midterm = Math.ceil(pct.midterm);
      if (has(pct, 'final')) pct.final = Math.ceil(pct.final);
      const coursework = ct === null ? null : Math.ceil(round2(ct));
      const finalScore = (coursework || 0) + (pct.midterm || 0) + (pct.final || 0);
      return {
        student_id: r.student_id, pct, coursework_total: coursework, final_score: finalScore,
        grade: letterGrade(finalScore, course.grade_boundaries), dropped,
      };
    });
  }

  return { ABSENT, CODE_VALUE, classify, sameCell, round2, letterGrade, mergeCourse, fillDefaultMax, computeGrades };
}
if (typeof module !== 'undefined') module.exports = (Csv) => gwGrades(Csv || require('./csv.js')());
