'use strict';
// grades.js navigation helpers (SPEC_web_tabs.md): categories, their columns, remembered tab and category.
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

const names = (cols) => cols.map((c) => c.name);

test('columnsOf per category', () => {
  const G = H.Grades();
  const course = H.courseOf(H.F2);
  assert.deepStrictEqual(names(G.columnsOf(course, 'homework')), ['hw1', 'hw2', 'hw3']);
  assert.deepStrictEqual(names(G.columnsOf(course, 'attendance')), ['13 Jan 2027', '20 Jan 2027', '27 Jan 2027']);
  assert.strictEqual(G.columnsOf(course, '*').length, course.columns.length);
  assert.deepStrictEqual(G.columnsOf(course, 'nothing'), []);
});

test('navCategories lists category_order, then unweighted pushed categories', () => {
  const G = H.Grades();
  const course = H.courseOf(H.F2);
  assert.deepStrictEqual(G.navCategories(course), course.category_order);
  const extra = Object.assign({}, course, { columns: course.columns.concat({ name: 'b1', header: 'b1', file: 'x',
    category: 'bonus' }) });
  assert.deepStrictEqual(G.navCategories(extra), course.category_order.concat('bonus'));
});

test('navFromMemory: first visit, current and older saved UI', () => {
  const G = H.Grades();
  const course = H.courseOf(H.F2);
  const first = G.firstCategory(course);
  assert.notStrictEqual(first, 'attendance');
  assert.deepStrictEqual(G.navFromMemory({}, course), { tab: 'summary', category: first });
  assert.deepStrictEqual(G.navFromMemory(null, course), { tab: 'summary', category: first });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'raw', category: 'homework' }, course),
    { tab: 'raw', category: 'homework' });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'analytics', category: '*' }, course),
    { tab: 'analytics', category: '*' });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, column: 'hw2', tab: 'scores' }, course),
    { tab: 'raw', category: first });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'attendance' }, course), { tab: 'raw', category: 'attendance' });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'table' }, course), { tab: 'raw', category: '*' });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'grading' }, course), { tab: 'grading', category: first });
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'raw', category: 'gone' }, course),
    { tab: 'raw', category: first }, 'a category gone after a re-push falls back');
  assert.deepStrictEqual(G.navFromMemory({ v: 1, tab: 'nope' }, course), { tab: 'summary', category: first });
});
