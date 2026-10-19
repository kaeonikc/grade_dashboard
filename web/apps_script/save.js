// save.js: what a Save or an Undo writes (web/SPEC.md "Saving", "Undo last save"). One factory, no globals (ADR 004).
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

  return { planSave, planUndo };
}
if (typeof module !== 'undefined') module.exports = gwSave;
