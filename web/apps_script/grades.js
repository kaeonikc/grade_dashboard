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

  // fmt_value(_cell_value(text)): what apply_edits stores for a typed text. With a '.' a float (integral ones lose
  // the '.0'), without one an int, else the trimmed text as it is. Exotic floats may differ textually from
  // Python's repr (0.00001 vs 1e-05) but never in meaning.
  const INT = /^[+-]?\d(_?\d)*$/;
  function canonicalValue(value) {
    const text = String(value == null ? '' : value).trim();
    if (text.includes('.')) {
      if (!FLOAT.test(text)) return text;
      const x = Number(text.replace(/_/g, ''));
      return Number.isInteger(x) ? BigInt(x).toString() : String(x);
    }
    return INT.test(text) ? BigInt(text.replace(/_/g, '')).toString() : text;
  }

  // Typed score text (S3.7): a number >= 0 with '.', blank or ขส. Refusal reasons: comma, negative, other.
  const TYPED = /^(\d+(\.\d*)?|\.\d+)$/;
  function validateTyped(value) {
    const text = String(value == null ? '' : value).trim();
    if (text === '' || text === ABSENT || TYPED.test(text)) return { ok: true, value: canonicalValue(text) };
    if (/^[\d.,]+$/.test(text) && /\d,\d/.test(text)) return { ok: false, reason: 'comma' };
    if (/^-(\d+(\.\d*)?|\.\d+)$/.test(text)) return { ok: false, reason: 'negative' };
    return { ok: false, reason: 'other' };
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

  // The letter scale, highest first; F is never a key (SPEC_grade_order.md D1).
  const GRADE_SCALE = ['A', 'B+', 'B', 'C+', 'C', 'D+', 'D'];
  const byText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  // The letters of a saved boundaries map in scale order, whatever its key order (key order doesn't survive the trip
  // to the browser). A letter outside the scale goes before the first letter with a lower saved threshold.
  function gradeOrder(saved) {
    const keys = Object.keys(saved || {});
    const order = GRADE_SCALE.filter((g) => keys.includes(g));
    const unknown = keys.filter((k) => !GRADE_SCALE.includes(k)).sort((a, b) => saved[b] - saved[a] || byText(a, b));
    for (const u of unknown) {
      const i = order.findIndex((g) => saved[g] < saved[u]);
      order.splice(i < 0 ? order.length : i, 0, u);
    }
    return order;
  }

  // Each letter's interval as grade-tui writes it, then F: [{letter, text}]. values must descend along order.
  function gradeRanges(order, values) {
    const out = order.map((g, i) => ({
      letter: g, text: i === 0 ? 'X ≥ ' + values[g] : values[g] + ' ≤ X < ' + values[order[i - 1]],
    }));
    out.push({ letter: 'F', text: order.length ? 'X < ' + values[order[order.length - 1]] : '' });
    return out;
  }

  // Students per letter (order, then F): [{letter, count, pct}].
  function distribution(grades, order) {
    const counts = new Map();
    for (const g of grades) counts.set(g.grade, (counts.get(g.grade) || 0) + 1);
    const n = grades.length;
    return order.concat('F').map((letter) => {
      const count = counts.get(letter) || 0;
      return { letter, count, pct: n ? (count / n) * 100 : 0 };
    });
  }

  // grade-tui's grade_color_for as a class suffix: a, bp, b, cp, c, dp, d, f.
  function gradeClass(letter) {
    const g = String(letter == null ? '' : letter).trim();
    if (g.startsWith('A')) return 'a';
    for (const L of ['B', 'C', 'D']) {
      if (g === L + '+') return L.toLowerCase() + 'p';
      if (g.startsWith(L)) return L.toLowerCase();
    }
    return 'f';
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

  // A session header like `20 Jan 2027` -> '2027-01-20'; anything else (placeholders a1..aN, totals) -> null.
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function sessionDate(header) {
    const m = /^(\d{1,2}) ([A-Z][a-z]{2}) (\d{4})$/.exec(String(header == null ? '' : header).trim());
    const month = m ? MONTHS.indexOf(m[2]) : -1;
    if (month < 0) return null;
    const d = new Date(Date.UTC(+m[3], month, +m[1]));
    if (d.getUTCDate() !== +m[1]) return null;
    return d.toISOString().slice(0, 10);
  }

  // Fill Column (S7): the cells that change when `value` goes in `column`, over every row. mode 'empty' takes only
  // blank cells, 'whole' every cell; an unsaved value (overlay) counts as the cell's value, and a cell that already
  // means `value` is left out. Returns [{student_id, value}].
  function fillTargets(rows, overlay, column, value, mode) {
    const edits = new Map();
    for (const e of overlay || []) if (e.column === column) edits.set(e.student_id, e.value);
    const targets = [];
    for (const r of rows) {
      const now = edits.has(r.student_id) ? edits.get(r.student_id) : (r.cells[column] || '');
      if (mode === 'empty' && now.trim() !== '') continue;
      if (!sameCell(now, value)) targets.push({ student_id: r.student_id, value });
    }
    return targets;
  }

  return {
    ABSENT, CODE_VALUE, classify, sameCell, canonicalValue, validateTyped, round2, letterGrade, mergeCourse,
    fillDefaultMax, computeGrades, sessionDate, fillTargets, GRADE_SCALE, gradeOrder, gradeRanges, distribution,
    gradeClass,
  };
}
if (typeof module !== 'undefined') module.exports = (Csv) => gwGrades(Csv || require('./csv.js')());
