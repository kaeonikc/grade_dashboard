// csv.js: CSV text as Python's csv module reads it (web/SPEC.md "CSV handling"). One factory, no globals (ADR 004).
function gwCsv() {
  'use strict';

  const BOM = '﻿';

  // Python's csv.reader, excel dialect, over text opened with newline='': a record ends at \r\n, \n or a lone \r
  // outside quotes; quoted fields keep their newlines; "" inside quotes is one "; text after a closing quote is
  // kept (non-strict); a blank line is an empty record.
  function records(text) {
    const out = [];
    let fields = [];
    let field = '';
    let state = 'record';  // record | field | unquoted | quoted | quote | crnl
    const save = () => { fields.push(field); field = ''; };
    const endLine = () => {
      if (state === 'quoted') { return; }
      if (state === 'field' || state === 'unquoted' || state === 'quote') save();
      out.push(fields);
      fields = [];
      state = 'record';
    };
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      const nl = c === '\n' || c === '\r';
      if (state === 'record') state = nl ? 'crnl' : 'field';
      if (state === 'field') {
        if (nl) { save(); state = 'crnl'; } else if (c === '"') state = 'quoted';
        else if (c === ',') save();
        else { field += c; state = 'unquoted'; }
      } else if (state === 'unquoted') {
        if (nl) { save(); state = 'crnl'; } else if (c === ',') { save(); state = 'field'; } else field += c;
      } else if (state === 'quoted') {
        if (c === '"') state = 'quote'; else field += c;
      } else if (state === 'quote') {
        if (c === '"') { field += c; state = 'quoted'; } else if (c === ',') { save(); state = 'field'; }
        else if (nl) { save(); state = 'crnl'; } else { field += c; state = 'unquoted'; }
      }
      if (c === '\n' || (c === '\r' && text[i + 1] !== '\n')) endLine();
    }
    if (state === 'quoted') { save(); out.push(fields); } else if (state !== 'record') endLine();
    return out;
  }

  // {header, rows, bom, eol} like csvio.read_csv_text: rows shorter than the header are padded with blanks.
  function parse(text) {
    const bom = text.startsWith(BOM);
    const body = bom ? text.slice(1) : text;
    const eol = body.includes('\r\n') ? '\r\n' : '\n';
    const recs = records(body);
    if (!recs.length) return { header: [], rows: [], bom, eol };
    const header = recs[0];
    const pad = (r) => (r.length < header.length ? r.concat(Array(header.length - r.length).fill('')) : r);
    const rows = recs.slice(1).map(pad);
    return { header, rows, bom, eol };
  }

  return { parse };
}
if (typeof module !== 'undefined') module.exports = gwCsv;
