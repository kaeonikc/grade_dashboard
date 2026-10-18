'use strict';
// grades.validateTyped / canonicalValue / sameCell (S3.5-S3.7, edges 13, 41).
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

test('ac3_7 allowed values', () => {
  const G = H.Grades();
  for (const [text, value] of [['9', '9'], ['8.5', '8.5'], ['0', '0'], ['', ''], ['ขส', 'ขส'], ['.5', '0.5'],
    [' 9 ', '9'], ['08', '8'], ['8.50', '8.5'], ['8.0', '8'], ['5.', '5']]) {
    const r = G.validateTyped(text);
    assert.strictEqual(r.ok, true, JSON.stringify(text));
    assert.strictEqual(r.value, value, JSON.stringify(text));
  }
});

test('ac3_7 comma refused', () => {
  const G = H.Grades();
  assert.deepStrictEqual(G.validateTyped('8,5'), { ok: false, reason: 'comma' });
});

test('ac3_7 negative refused', () => {
  const G = H.Grades();
  assert.deepStrictEqual(G.validateTyped('-3'), { ok: false, reason: 'negative' });
  assert.deepStrictEqual(G.validateTyped('-0.5'), { ok: false, reason: 'negative' });
});

test('ac3_7 other refused', () => {
  const G = H.Grades();
  for (const text of ['abc', 'ข ส', '12a', '1e5', '8.5.1', 'P', 'NaN', 'Infinity', '+3']) {
    assert.deepStrictEqual(G.validateTyped(text), { ok: false, reason: 'other' }, JSON.stringify(text));
  }
});

test('ac3_5 above max accepted', () => {
  const G = H.Grades();
  assert.deepStrictEqual(G.validateTyped('12'), { ok: true, value: '12' });
});

test('canonicalValue matches Python', () => {
  const G = H.Grades();
  const golden = H.loadGoldenFile('canonical.json');
  const entries = Array.isArray(golden) ? golden : Object.entries(golden).map(([input, v]) => ({ input, ...v }));
  assert.ok(entries.length >= 16);
  const exotic = new Set(['0.00001', '10000000000000000.0', '0.30000000000000004', '12345678.9']);
  for (const e of entries) {
    const got = G.canonicalValue(e.input);
    if (exotic.has(e.input)) assert.ok(G.sameCell(got, e.canonical), e.input + ' -> ' + got + ' vs ' + e.canonical);
    else assert.strictEqual(got, e.canonical, JSON.stringify(e.input));
    assert.deepStrictEqual(G.classify(e.input), e.classify, 'classify ' + JSON.stringify(e.input));
  }
});

test('sameCell compares by meaning', () => {
  const G = H.Grades();
  assert.strictEqual(G.sameCell('9.0', '9'), true);
  assert.strictEqual(G.sameCell(' ขส ', 'ขส'), true);
  assert.strictEqual(G.sameCell('', ' '), true);
  assert.strictEqual(G.sameCell('', 'nan'), true);
  assert.strictEqual(G.sameCell('9', '8'), false);
  assert.strictEqual(G.sameCell('', '0'), false);
  assert.strictEqual(G.sameCell('ขส', ''), false);
  assert.strictEqual(G.sameCell('P', 'P'), true);
  assert.strictEqual(G.sameCell('P', 'A'), false);
});
