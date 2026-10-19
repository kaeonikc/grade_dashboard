// csv.js: CSV text as Python's csv module reads it (web/SPEC.md "CSV handling"). One factory, no globals (ADR 004).
function gwCsv() {
  'use strict';

  const BOM = '﻿';

  // Python's csv.reader, excel dialect, over text opened with newline='': a record ends at \r\n, \n or a lone \r
  // outside quotes; quoted fields keep their newlines; "" inside quotes is one "; text after a closing quote is
  // kept (non-strict); a blank line is an empty record. Each record also keeps where it starts and each field's
  // [start, end) span in the text (quotes included), for splice.
  function records(text) {
    const out = [];
    let rec = null;
    let field = '';
    let start = 0;
    let state = 'record';  // record | field | unquoted | quoted | quote | crnl
    const save = (end) => { rec.fields.push(field); rec.spans.push([start, end]); field = ''; };
    const endLine = (i) => {
      if (state === 'quoted') { return; }
      if (state === 'field' || state === 'unquoted' || state === 'quote') save(i);
      out.push(rec);
      rec = null;
      state = 'record';
    };
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      const nl = c === '\n' || c === '\r';
      if (state === 'record') {
        rec = { at: i, fields: [], spans: [] };
        start = i;
        state = nl ? 'crnl' : 'field';
      }
      if (state === 'field') {
        if (nl) { save(i); state = 'crnl'; } else if (c === '"') state = 'quoted';
        else if (c === ',') { save(i); start = i + 1; } else { field += c; state = 'unquoted'; }
      } else if (state === 'unquoted') {
        if (nl) { save(i); state = 'crnl'; } else if (c === ',') { save(i); start = i + 1; state = 'field'; }
        else field += c;
      } else if (state === 'quoted') {
        if (c === '"') state = 'quote'; else field += c;
      } else if (state === 'quote') {
        if (c === '"') { field += c; state = 'quoted'; } else if (c === ',') { save(i); start = i + 1; state = 'field'; }
        else if (nl) { save(i); state = 'crnl'; } else { field += c; state = 'unquoted'; }
      }
      if (c === '\n' || (c === '\r' && text[i + 1] !== '\n')) endLine(i);
    }
    if (state === 'quoted') { save(text.length); out.push(rec); } else if (state !== 'record') endLine(text.length);
    return out;
  }

  // {header, rows, bom, eol} like csvio.read_csv_text: rows shorter than the header are padded with blanks.
  function parse(text) {
    const bom = text.startsWith(BOM);
    const body = bom ? text.slice(1) : text;
    const eol = body.includes('\r\n') ? '\r\n' : '\n';
    const recs = records(body).map((r) => r.fields);
    if (!recs.length) return { header: [], rows: [], bom, eol };
    const header = recs[0];
    const pad = (r) => (r.length < header.length ? r.concat(Array(header.length - r.length).fill('')) : r);
    const rows = recs.slice(1).map(pad);
    return { header, rows, bom, eol };
  }

  // csv.writer's QUOTE_MINIMAL for one field.
  function quote(value) {
    return /[",\r\n]/.test(value) ? '"' + value.replace(/"/g, '""') + '"' : value;
  }

  // The text with only the targeted cells replaced (S8.6): targets [{row, col, value}], row 0 = the first row
  // after the header. Every other byte (BOM, line endings, quoting, other cells) stays. A row shorter than the
  // target column gets `,` padding after its last field.
  function splice(text, targets) {
    const bom = text.startsWith(BOM);
    const body = bom ? text.slice(1) : text;
    const recs = records(body);
    const byRow = new Map();
    for (const t of targets) {
      if (!recs[t.row + 1]) throw new Error('splice: no row ' + t.row);
      if (!byRow.has(t.row)) byRow.set(t.row, new Map());
      byRow.get(t.row).set(t.col, quote(String(t.value)));
    }
    const parts = [];  // [start, end, text], applied from the end of the text backwards
    for (const [row, cols] of byRow) {
      const rec = recs[row + 1];
      const n = rec.spans.length;
      let pad = '';
      for (const [col, value] of cols) if (col < n) parts.push([rec.spans[col][0], rec.spans[col][1], value]);
      const last = Math.max(...cols.keys());
      for (let col = n; col <= last; col++) pad += (col > 0 ? ',' : '') + (cols.has(col) ? cols.get(col) : '');
      if (pad) {
        const at = n ? rec.spans[n - 1][1] : rec.at;
        parts.push([at, at, pad]);
      }
    }
    parts.sort((a, b) => b[0] - a[0]);
    let out = body;
    for (const [s, e, value] of parts) out = out.slice(0, s) + value + out.slice(e);
    return (bom ? BOM : '') + out;
  }

  return { parse, splice };
}
if (typeof module !== 'undefined') module.exports = gwCsv;
