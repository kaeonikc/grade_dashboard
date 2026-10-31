'use strict';
// The page's scripts (Index.html: the client core, client_state.html, client_views.html) share one global scope. A
// top-level name defined twice is a silent override for a function (client_views' chip handler `pickSection(sec)`
// replaced client_state's `pickSection(course, iso, remembered)`, and every course with sections failed to open on
// the phone) and an error for const/let. The node tests load the files separately, so this checks the names.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const H = require('./helpers.js');

const TOP = /^(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z_$][\w$]*)/gm;

function names(text) {
  return Array.from(text.matchAll(TOP), (m) => m[1]);
}

test('no top-level name is defined twice across the page scripts', () => {
  const index = fs.readFileSync(path.join(H.APPS, 'Index.html'), 'utf8');
  const sources = {
    'Index.html': index,
    core: ['Csv', 'Grades', 'Journal', 'Save'].map((n) => 'const ' + n)  // Code.js clientCore_()
      .concat(['gwCsv', 'gwGrades', 'gwJournal', 'gwSave'].map((n) => 'function ' + n)).join('\n'),
    'client_state.html': fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8'),
    'client_views.html': fs.readFileSync(path.join(H.APPS, 'client_views.html'), 'utf8'),
  };
  const where = new Map();
  const twice = [];
  for (const [file, text] of Object.entries(sources)) {
    for (const name of names(text)) {
      if (where.has(name)) twice.push(name + ' (' + where.get(name) + ', ' + file + ')');
      else where.set(name, file);
    }
  }
  assert.deepStrictEqual(twice, []);
  assert.ok(where.get('pickSection') === 'client_state.html' && where.get('tapSection') === 'client_views.html');
});
