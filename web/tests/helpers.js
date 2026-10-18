'use strict';
// Shared node test helpers (web/SPEC.md "Layer 1"). Not a test file: it doesn't end in .test.js.
// Modules are loaded lazily, inside each test, so a missing module fails each test on its own.
const fs = require('node:fs');
const path = require('node:path');

const WEB = path.resolve(__dirname, '..');
const APPS = path.join(WEB, 'apps_script');
const FIXTURES = path.join(__dirname, 'fixtures');
const GOLDEN = path.join(__dirname, 'golden');
const JOURNALS = path.join(FIXTURES, 'journals');
const F1 = '9_ฟิสิกส์จำลอง_grading';
const F2 = '9_กลศาสตร์ทดลอง_grading';
const F3 = '9_ไฟฟ้าจำลอง_grading';
const F4 = '9_ดาราศาสตร์จำลอง_grading';
const P1 = '9_ฟิสิกส์จำลอง';
const PUSH = 'p-20270119-201500';

// ADR 004: each pure module is one factory function with a CommonJS footer.
function Csv() { return require(path.join(APPS, 'csv.js'))(); }
function Grades() { return require(path.join(APPS, 'grades.js'))(); }
function Journal() { return require(path.join(APPS, 'journal.js'))(); }
function Save() { return require(path.join(APPS, 'save.js'))(Csv(), Grades()); }

// Text as Drive gives it to the server: UTF-8, a BOM kept as U+FEFF.
function readText(p) { return fs.readFileSync(p).toString('utf8'); }

function loadGolden(fixture) {
  return JSON.parse(fs.readFileSync(path.join(GOLDEN, fixture + '.json'), 'utf8'));
}

function loadGoldenFile(name) {
  return JSON.parse(fs.readFileSync(path.join(GOLDEN, name), 'utf8'));
}

// course.json of a fixture, as web-push builds it (from the golden file, written by make_golden.py).
function courseOf(fixture) { return loadGolden(fixture).course; }

// {roster, files} texts of a fixture course, keyed like loadCourse's reply.
function textsOf(course, fixture) {
  const dir = path.join(FIXTURES, fixture || course.folder);
  const files = {};
  for (const f of course.files) files[f] = readText(path.join(dir, f));
  return { roster: readText(path.join(dir, course.roster)), files };
}

function rowsOf(course, fixture) {
  const t = textsOf(course, fixture);
  return Grades().mergeCourse(course, t.roster, t.files);
}

function journalText(name) { return readText(path.join(JOURNALS, name)); }

function journalLines(name) {
  return journalText(name).split('\n').filter((l) => l.trim() !== '');
}

function variants() {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, 'variants.json'), 'utf8'));
}

// A course with the variant's weights/boundaries swapped in (the overlay is the variant's edits).
function withVariant(course, v) {
  const c = JSON.parse(JSON.stringify(course));
  if (v.weights) c.weights = v.weights;
  if (v.grade_boundaries) c.grade_boundaries = v.grade_boundaries;
  return c;
}

module.exports = {
  WEB, APPS, FIXTURES, GOLDEN, JOURNALS, F1, F2, F3, F4, P1, PUSH,
  Csv, Grades, Journal, Save, readText, loadGolden, loadGoldenFile, courseOf, textsOf, rowsOf,
  journalText, journalLines, variants, withVariant,
};
