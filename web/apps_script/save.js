// save.js: what a Save, an Undo or a config save writes (web/SPEC.md "Saving", "Undo last save", "Config save").
// One factory, no globals (ADR 004). Injected into the browser too, so the Grading form checks what the server checks.
// Csv = gwCsv(), Grades = gwGrades(Csv).
function gwSave(Csv, Grades) {
  'use strict';

  const CODES = ['P', 'L', 'A', 'X', ''];  // what taps and Fill put in an attendance cell (an existing EA is kept)

  // The canonical value written for an edit, or null when the server refuses it (S3.7).
  function accepted(value, column) {
    const text = String(value == null ? '' : value).trim();
    if (column.category === 'attendance') return CODES.indexOf(text) >= 0 ? text : null;
    const r = Grades.validateTyped(text);
    return r.ok ? r.value : null;
  }

  // Locates each edit's cell, checks it against the Drive text and splices the changes (SPEC "Saving" step 2).
  // files = {<rel path>: text} for the edited columns' files. Duplicate IDs: the first row is checked, every row
  // is set (edge 6). `restoring` (Undo, roll-forward) writes each value as it is, unvalidated: it puts back text
  // that was in the file before. Returns {changes: [{student_id, column, file, value, original}], already,
  // conflicts: [{student_id, column, now, reason}], texts: {<rel path>: spliced text} for changed files only}.
  function planSave(files, course, edits, restoring) {
    const docs = new Map();
    const docOf = (file) => {
      if (!docs.has(file)) {
        const d = Csv.parse(files[file]);
        docs.set(file, { header: d.header.map((h) => h.trim()), rows: d.rows, targets: [] });
      }
      return docs.get(file);
    };
    const changes = [];
    const already = [];
    const conflicts = [];
    for (const e of edits) {
      const sid = String(e.student_id).trim();
      const conflict = (reason, now) => conflicts.push({ student_id: sid, column: e.column, now, reason });
      const col = course.columns.find((c) => c.name === e.column);
      const d = col && typeof files[col.file] === 'string' ? docOf(col.file) : null;
      const ci = d ? d.header.indexOf(col.header.trim()) : -1;
      const iId = d ? d.header.indexOf('Student ID') : -1;
      const rows = [];
      if (ci >= 0 && iId >= 0) d.rows.forEach((r, i) => { if ((r[iId] || '').trim() === sid) rows.push(i); });
      if (!rows.length) {
        conflict('not found', null);
        continue;
      }
      const now = d.rows[rows[0]][ci];
      const value = restoring ? String(e.value) : accepted(e.value, col);
      if (value === null) {
        conflict('invalid', now);
      } else if (Grades.sameCell(now, value)) {
        already.push({ student_id: sid, column: e.column, value });
      } else if (Grades.sameCell(now, e.original)) {
        changes.push({ student_id: sid, column: e.column, file: col.file, value, original: now });
        for (const row of rows) d.targets.push({ row, col: ci, value });
      } else {
        conflict('changed', now);
      }
    }
    const texts = {};
    for (const [file, d] of docs) if (d.targets.length) texts[file] = Csv.splice(files[file], d.targets);
    return { changes, already, conflicts, texts };
  }

  // The inverse edits of a batch's cell lines, in seq order: each puts back what the save replaced.
  function planUndo(lines, batch) {
    return lines.filter((l) => l.batch === batch && l.kind === 'cell').sort((a, b) => a.seq - b.seq)
      .map((l) => ({ student_id: l.student_id, column: l.column, value: l.original, original: l.value }));
  }

  // ---- config (weights, grade_boundaries) ----
  const PARTS = ['weights', 'grade_boundaries'];

  // A typed weight or boundary: {ok, value: number} or {ok: false, reason: 'empty'|'comma'|'negative'|'nan'} (S10.3).
  function configNumber(text) {
    const t = String(text == null ? '' : text).trim();
    if (t === '') return { ok: false, reason: 'empty' };
    const r = t === Grades.ABSENT ? { ok: false, reason: 'other' } : Grades.validateTyped(t);
    if (r.ok) return { ok: true, value: Number(t) };
    return { ok: false, reason: r.reason === 'other' ? 'nan' : r.reason };
  }

  // Every problem of a form, in the given key order (boundaries: Grades.gradeOrder): {field, reason} from configNumber,
  // or for boundaries {field, reason: 'order', upper} when a letter isn't lower than the nearest valid letter above it
  // (S10.4).
  function configProblems(part, keys, form) {
    const problems = [];
    let above = null;
    for (const k of keys) {
      const n = configNumber(form[k]);
      if (!n.ok) {
        problems.push({ field: k, reason: n.reason });
        continue;
      }
      if (part === 'grade_boundaries' && above && !(n.value < above.value)) {
        problems.push({ field: k, reason: 'order', upper: above.key });
      }
      above = { key: k, value: n.value };
    }
    return problems;
  }

  // Same keys with the same numbers (key order aside).
  function sameConfig(a, b) {
    const ka = Object.keys(a || {});
    return ka.length === Object.keys(b || {}).length &&
      ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && a[k] === b[k]);
  }

  // The weights' sum as shown (1.05), rounded so float noise like 1.0000000000000002 reads 1.
  function weightTotal(weights) {
    const total = Object.keys(weights).reduce((s, k) => s + weights[k], 0);
    return Math.round(total * 1e6) / 1e6;
  }

  // `weights sum to 1.05` when the weights don't add up to 1 (a warning, never a refusal: S10.2, edge 45).
  function sumWarning(weights) {
    const total = weightTotal(weights);
    return total === 1 ? null : 'weights sum to ' + total;
  }

  // A config save (SPEC "Config save"). value = {key: text} as typed, original = {key: number} as loaded.
  // Refusals: STALE_CONFIG with `current` when Drive changed since the form was loaded (checked first, so the
  // teacher sees the Drive values), INVALID with `field` and `reason` ('part', 'keys', configNumber's, or 'order' with `upper`).
  // Success: {ok, course: a new course.json with only `part` replaced, value: {key: number} in the stored key
  // order for weights and in scale order (Grades.gradeOrder) for boundaries, warning}.
  function planConfig(course, part, value, original) {
    const invalid = (field, reason) => ({ ok: false, code: 'INVALID', field, reason });
    if (PARTS.indexOf(part) < 0 || !course[part]) return invalid('part', 'part');
    const current = course[part];
    if (!sameConfig(original, current)) return { ok: false, code: 'STALE_CONFIG', current };
    const keys = part === 'grade_boundaries' ? Grades.gradeOrder(current) : Object.keys(current);
    const extra = Object.keys(value || {}).find((k) => keys.indexOf(k) < 0);
    const missing = keys.find((k) => !Object.prototype.hasOwnProperty.call(value || {}, k));
    if (extra !== undefined || missing !== undefined) return invalid(extra !== undefined ? extra : missing, 'keys');
    const problems = configProblems(part, keys, value);
    if (problems.length) return Object.assign({ ok: false, code: 'INVALID' }, problems[0]);
    const next = {};
    for (const k of keys) next[k] = configNumber(value[k]).value;
    return {
      ok: true, course: Object.assign({}, course, { [part]: next }), value: next,
      warning: part === 'weights' ? sumWarning(next) : null,
    };
  }

  return { planSave, planUndo, configNumber, configProblems, sameConfig, weightTotal, sumWarning, planConfig };
}
if (typeof module !== 'undefined') module.exports = gwSave;
