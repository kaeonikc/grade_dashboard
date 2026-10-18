'use strict';
// csv.js: parse like Python's csv module (read side, T4) and cell splice (write side, T7). S8.6, edges 1, 2, 4, 5.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const H = require('./helpers.js');

function fixtureCsvFiles() {
  const out = [];
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.csv')) out.push(p);
    }
  };
  walk(H.FIXTURES);
  return out.sort();
}
const rel = (p) => path.relative(H.FIXTURES, p).split(path.sep).join('/');
const CSV_DIR = path.join(H.FIXTURES, 'csv');

test('csv parse matches Python csv', () => {
  const C = H.Csv();
  const golden = H.loadGoldenFile('csv_rows.json');
  const files = fixtureCsvFiles();
  assert.ok(files.length >= 25);
  for (const p of files) {
    const want = golden[rel(p)];
    assert.ok(want, 'csv_rows.json has ' + rel(p));
    const got = C.parse(H.readText(p));
    assert.deepStrictEqual(got.header, want.header, rel(p) + ' header');
    assert.deepStrictEqual(got.rows, want.rows, rel(p) + ' rows');
    assert.strictEqual(got.bom, want.bom, rel(p) + ' bom');
    assert.strictEqual(got.eol, want.eol, rel(p) + ' eol');
  }
});

test('edge1 BOM kept', () => {
  const C = H.Csv();
  const text = H.readText(path.join(CSV_DIR, 'bom_crlf_quotes.csv'));
  const doc = C.parse(text);
  assert.strictEqual(doc.bom, true);
  assert.strictEqual(doc.header[0], 'Student ID');
  const out = C.splice(text, [{ row: 0, col: 3, value: '9' }]);
  assert.ok(out.startsWith('﻿Student ID,'));
  assert.ok(Buffer.from(out, 'utf8').subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])));
});

test('edge2 CRLF kept', () => {
  const C = H.Csv();
  const text = H.readText(path.join(CSV_DIR, 'bom_crlf_quotes.csv'));
  assert.strictEqual(C.parse(text).eol, '\r\n');
  const out = C.splice(text, [{ row: 2, col: 3, value: '8' }]);
  assert.strictEqual(out.split('\r\n').length, text.split('\r\n').length);
  assert.ok(!/[^\r]\n/.test(out), 'no bare LF');
  assert.ok(out.includes('9900000403,นายทดลอง มีชื่อ,ขส,8,7\r\n'), out);
  assert.strictEqual(C.parse(H.readText(path.join(CSV_DIR, 'short_rows.csv'))).eol, '\n');
});

test('edge4 quoted names round-trip', () => {
  const C = H.Csv();
  const text = H.readText(path.join(CSV_DIR, 'bom_crlf_quotes.csv'));
  const doc = C.parse(text);
  assert.strictEqual(doc.rows[0][1], 'นายสมมติ, ทดสอบ');
  assert.strictEqual(doc.rows[1][1], 'นางสาว "ฝน" ตัวอย่าง');
  const out = C.splice(text, [{ row: 1, col: 2, value: '4' }]);
  assert.ok(out.includes('\r\n9900000402,"นางสาว ""ฝน"" ตัวอย่าง",4,9.5,9.5\r\n'), out);
  assert.ok(out.includes('9900000401,"นายสมมติ, ทดสอบ",8,,8'));
  const nl = H.readText(path.join(CSV_DIR, 'embedded_newline.csv'));
  const d2 = C.parse(nl);
  assert.strictEqual(d2.rows.length, 2);
  assert.strictEqual(d2.rows[0][1], 'นายสมมติ\nบรรทัดสอง');
  assert.strictEqual(C.splice(nl, [{ row: 1, col: 2, value: '3' }]),
    nl.replace('9900000412,นางสาวปกติ ดี,,0', '9900000412,นางสาวปกติ ดี,3,0'));
});

test('edge5 padded IDs read as text', () => {
  const C = H.Csv();
  const doc = C.parse(H.readText(path.join(CSV_DIR, 'padded_ids.csv')));
  assert.strictEqual(doc.rows[0][0], ' 9900000441 ');
  assert.strictEqual(doc.rows[1][0], '9900000442 ');
});

function commonEnds(a, b) {
  let p = 0;
  while (p < a.length && p < b.length && a[p] === b[p]) p++;
  let s = 0;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
  return [p, s];
}

test('ac8_6 splice changes only target spans', () => {
  const C = H.Csv();
  let n = 0;
  for (const p of fixtureCsvFiles().filter((f) => f.includes(path.sep + 'data' + path.sep))) {
    const text = H.readText(p);
    const doc = C.parse(text);
    const col = 2;
    const out = C.splice(text, [{ row: 0, col, value: 'ขส' }]);
    const after = C.parse(out);
    const want = doc.rows.map((r) => r.slice());
    want[0][col] = 'ขส';
    assert.deepStrictEqual(after.rows, want, rel(p));
    assert.deepStrictEqual(after.header, doc.header, rel(p));
    assert.strictEqual(after.bom, doc.bom, rel(p));
    assert.strictEqual(after.eol, doc.eol, rel(p));
    if (doc.rows[0][col] !== 'ขส') {
      const [pre, suf] = commonEnds(text, out);
      const oldPart = text.slice(pre, text.length - suf);
      assert.ok(!/[,\r\n]/.test(oldPart), rel(p) + ': change spans more than one field: ' + JSON.stringify(oldPart));
    }
    n++;
  }
  assert.ok(n >= 20);
  // a short row is padded with commas up to the target column
  const short = H.readText(path.join(CSV_DIR, 'short_rows.csv'));
  assert.strictEqual(C.splice(short, [{ row: 1, col: 3, value: '9' }]),
    short.replace('9900000422,นางสาวสั้น สอง\n', '9900000422,นางสาวสั้น สอง,,9\n'));
  // the last row of a file without a final newline stays without one
  const nofinal = H.readText(path.join(CSV_DIR, 'no_final_newline.csv'));
  const o2 = C.splice(nofinal, [{ row: 1, col: 2, value: '10' }]);
  assert.strictEqual(o2, nofinal.replace('นางสาวท้าย สุด,6,6', 'นางสาวท้าย สุด,10,6'));
  // Python-compatible minimal quoting for a value that needs it
  const o3 = C.splice(short, [{ row: 2, col: 2, value: 'a,b' }]);
  assert.ok(o3.includes('9900000423,นายยาว ครบ,"a,b",2,3\n'), o3);
  // several targets in one call, one of them in a quoted row
  const bq = H.readText(path.join(CSV_DIR, 'bom_crlf_quotes.csv'));
  const o4 = C.splice(bq, [{ row: 0, col: 3, value: '1' }, { row: 2, col: 2, value: '' }]);
  assert.deepStrictEqual(C.parse(o4).rows.map((r) => r.slice(2, 4)), [['8', '1'], ['', '9.5'], ['', '7']]);
});

test('splice of no targets returns identical bytes', () => {
  const C = H.Csv();
  for (const p of fixtureCsvFiles()) {
    const text = H.readText(p);
    assert.strictEqual(C.splice(text, []), text, rel(p));
  }
});
