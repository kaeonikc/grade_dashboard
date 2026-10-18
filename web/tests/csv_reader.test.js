'use strict';
// csv.js parse on shapes the fixture files can't hold. Expected values are Python's csv.reader output
// (padded like csvio.read_csv_text), checked once with python3 when this file was written.
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

const CASES = [
  ['lone CR ends a record', 'a,b\rc,d\r\ne', ['a', 'b'], [['c', 'd'], ['e', '']], '\r\n'],
  ['text after a closing quote is kept', 'h1,h2,h3\na,"b"c,d\n', ['h1', 'h2', 'h3'], [['a', 'bc', 'd']], '\n'],
  ['blank line is a blank row', 'x\n\ny\n', ['x'], [[''], ['y']], '\n'],
  ['unterminated quote runs to the end', 'h1,h2\na,"unterminated\nmore', ['h1', 'h2'],
    [['a', 'unterminated\nmore']], '\n'],
  ['trailing comma is an empty field', 'h1,h2,h3\na,b,', ['h1', 'h2', 'h3'], [['a', 'b', '']], '\n'],
  ['doubled quotes', 'h1,h2\n"""q""",z\n', ['h1', 'h2'], [['"q"', 'z']], '\n'],
  ['CRLF inside quotes is kept', 'h1,h2\r\na,"b\r\nc"\r\n', ['h1', 'h2'], [['a', 'b\r\nc']], '\r\n'],
];

for (const [name, text, header, rows, eol] of CASES) {
  test('csv reader: ' + name, () => {
    const doc = H.Csv().parse(text);
    assert.deepStrictEqual(doc.header, header);
    assert.deepStrictEqual(doc.rows, rows);
    assert.strictEqual(doc.eol, eol);
    assert.strictEqual(doc.bom, false);
  });
}

test('csv reader: empty text', () => {
  assert.deepStrictEqual(H.Csv().parse(''), { header: [], rows: [], bom: false, eol: '\n' });
});
