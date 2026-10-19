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

  // Python's round(x, 2): half to even on the exact binary value of x (not numpy's round2), then the nearest double.
  // BigInt() calls, not literals: the Apps Script parser rejects `1n`.
  function pyRound2(x) {
    if (!Number.isFinite(x) || x === 0) return x;
    const [ONE, TWO, HUNDRED] = [BigInt(1), BigInt(2), BigInt(100)];
    const dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, Math.abs(x));
    const hi = dv.getUint32(0);
    const bits = (hi >>> 20) & 0x7ff;
    let m = (BigInt(hi & 0xfffff) << BigInt(32)) | BigInt(dv.getUint32(4));
    if (bits) m |= ONE << BigInt(52);
    const e = (bits || 1) - 1075;
    if (e >= 0) return x;
    const num = HUNDRED * m;
    const den = ONE << BigInt(-e);
    let q = num / den;
    const rem2 = TWO * (num - q * den);
    if (rem2 > den || (rem2 === den && q % TWO === ONE)) q += ONE;
    const r = Number(q) / 100;
    return x < 0 ? -r : r;
  }

  // pandas' Series.quantile (numpy 'linear'): sorted ascending, numpy's _lerp.
  function quantile(sorted, q) {
    const idx = (sorted.length - 1) * q;
    const lo = Math.floor(idx);
    const t = idx - lo;
    const a = sorted[lo];
    const b = sorted[Math.min(lo + 1, sorted.length - 1)];
    const d = b - a;
    return t >= 0.5 ? b - d * (1 - t) : a + d * t;
  }

  // grade-tui's Analytics › Overview (tui_api._compute_analytics: overview, histogram, box_plot) over computeGrades
  // rows; rows (same order) give the outliers' names. Shapes and rounding match the golden JSON.
  function analytics(grades, rows) {
    const n = grades.length;
    const scores = grades.map((g) => Number(g.final_score) || 0);
    const sorted = scores.slice().sort((a, b) => a - b);
    const mean = n ? sum(scores) / n : 0;
    const passing = grades.filter((g) => g.grade !== 'F').length;
    const sd = n > 1 ? Math.sqrt(sum(scores.map((x) => (x - mean) ** 2)) / (n - 1)) : 0;
    const overview = {
      mean: n ? pyRound2(mean) : 0, median: n ? pyRound2(quantile(sorted, 0.5)) : 0, std_dev: n > 1 ? pyRound2(sd) : 0,
      pass_rate: n ? pyRound2((passing / n) * 100) : 0, passing_count: passing, total_count: n,
    };
    const histogram = [];
    if (n) {
      for (let i = 0; i < 10; i++) histogram.push({ label: i < 9 ? i * 10 + '-' + (i * 10 + 9) : '90-100', count: 0 });
      for (const x of scores) histogram[Math.min(9, Math.max(0, Math.floor(x / 10)))].count += 1;
    }
    if (!n) {
      return { overview, histogram, box_plot: { min: 0, q1: 0, median: 0, q3: 0, max: 0, mean: 0, whisker_low: 0,
        whisker_high: 0, skew_label: 'roughly symmetric', outliers: [] } };
    }
    const q1 = quantile(sorted, 0.25);
    const q2 = quantile(sorted, 0.5);
    const q3 = quantile(sorted, 0.75);
    const iqr = q3 - q1;
    const lowFence = q1 - 1.5 * iqr;
    const highFence = q3 + 1.5 * iqr;
    const inside = sorted.filter((x) => x >= lowFence && x <= highFence);
    const ratio = iqr > 0 ? (mean - q2) / iqr : 0;
    const names = new Map((rows || []).map((r) => [r.student_id, r.name]));
    const outliers = grades.map((g, i) => ({ g, x: scores[i] })).filter((o) => o.x < lowFence || o.x > highFence)
      .map((o) => ({ student_id: o.g.student_id, name: names.has(o.g.student_id) ? names.get(o.g.student_id) : '',
        final_score: o.x }))
      .sort((a, b) => a.final_score - b.final_score);
    return {
      overview, histogram,
      box_plot: {
        min: sorted[0], q1, median: q2, q3, max: sorted[n - 1], mean: pyRound2(mean),
        whisker_low: inside.length ? inside[0] : sorted[0],
        whisker_high: inside.length ? inside[inside.length - 1] : sorted[n - 1],
        skew_label: Math.abs(ratio) < 0.05 ? 'roughly symmetric' : ratio > 0 ? 'right-skewed (mean > median)'
          : 'left-skewed (mean < median)',
        outliers,
      },
    };
  }

  // ---- Navigation (SPEC_web_tabs.md): grade-tui's tabs and the ☰ categories menu. Pure, so node can test it ----
  const TABS = ['summary', 'raw', 'analytics', 'grading'];

  // Raw Details' categories: category_order, then any category of the pushed columns not in it.
  function navCategories(course) {
    const cats = course.category_order.slice();
    for (const c of course.columns) if (!cats.includes(c.category)) cats.push(c.category);
    return cats;
  }

  // The pushed columns of a category, in course.columns order ('*' = every column).
  function columnsOf(course, category) {
    return course.columns.filter((c) => category === '*' || c.category === category);
  }

  // The first category with a score column, else the first with any column, else the first listed.
  function firstCategory(course) {
    const cats = navCategories(course);
    return cats.find((k) => k !== 'attendance' && columnsOf(course, k).length) ||
      cats.find((k) => columnsOf(course, k).length) || cats[0] || '*';
  }

  // {tab, category} from a course's remembered UI (gw:ui:<folder>, v 1). Older pages saved tab = the view they
  // showed: scores, attendance, table or grading. First visit: Summary.
  function navFromMemory(ui, course) {
    const old = { scores: ['raw', null], attendance: ['raw', 'attendance'], table: ['raw', '*'] };
    let tab = (ui && ui.tab) || 'summary';
    let category = ui && ui.category;
    if (has(old, tab)) [tab, category] = [old[tab][0], category || old[tab][1]];
    if (!TABS.includes(tab)) tab = 'summary';
    if (category !== '*' && !navCategories(course).includes(category)) category = firstCategory(course);
    return { tab, category };
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

  // ---- Attendance grid (SPEC_attendance_grid.md) ----
  const ATT_KIND = { P: 'P', L: 'L', A: 'A', X: 'X', EA: 'X' };
  const attZero = () => ({ P: 0, L: 0, A: 0, X: 0, blank: 0 });

  // Per student and per session, over the sessions held so far (dated today or earlier; an undated header once any
  // row has a code there). Points as computeGrades (CODE_VALUE); EA counts as X; an invalid code counts nowhere.
  // textOf(row, column) = the cell with unsaved edits applied; today = 'YYYY-MM-DD'.
  // -> {students: Map(student_id -> {held, total, pct, counts, atRisk}), sessions: [{name, held, present, counts}]}
  function attendanceStats(rows, sessions, textOf, today) {
    const code = (r, s) => String(textOf(r, s.name) == null ? '' : textOf(r, s.name)).trim();
    const held = sessions.map((s) => {
      const d = sessionDate(s.header);
      return d ? d <= today : rows.some((r) => code(r, s) !== '');
    });
    const perSession = sessions.map((s, i) => ({ name: s.name, held: held[i], present: 0, counts: attZero() }));
    const students = new Map();
    for (const r of rows) {
      const st = { held: 0, total: 0, pct: null, counts: attZero(), atRisk: false };
      sessions.forEach((s, i) => {
        const c = code(r, s);
        const kind = c === '' ? 'blank' : ATT_KIND[c];
        if (kind) perSession[i].counts[kind] += 1;
        if (kind && kind !== 'blank' && kind !== 'A') perSession[i].present += 1;
        if (!held[i]) return;
        st.held += 1;
        if (has(CODE_VALUE, c)) st.total += CODE_VALUE[c];
        if (kind) st.counts[kind] += 1;
      });
      if (st.held) {
        // Points are multiples of 0.2: tenths as an integer keep 80% exact (no 79.999… from float sums).
        st.pct = (Math.round(st.total * 10) * 10) / st.held;
        st.atRisk = st.pct < 80;
      }
      students.set(r.student_id, st);
    }
    return { students, sessions: perSession };
  }

  // `9.6 / 10 · 96%` (the % rounded down, so a flagged row never reads 80%), or `—` before the first held session.
  function fmtAttTotal(st) {
    if (!st || !st.held) return '—';
    return st.total.toFixed(1) + ' / ' + st.held + ' · ' + Math.floor(st.pct) + '%';
  }

  // `16 Jun 2026` -> `16/6`; an undated header as written.
  function shortDate(header) {
    const d = sessionDate(header);
    return d ? +d.slice(8, 10) + '/' + +d.slice(5, 7) : String(header == null ? '' : header);
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
    gradeClass, pyRound2, quantile, analytics, TABS, navCategories, columnsOf, firstCategory, navFromMemory,
    attendanceStats, fmtAttTotal, shortDate,
  };
}
if (typeof module !== 'undefined') module.exports = (Csv) => gwGrades(Csv || require('./csv.js')());
