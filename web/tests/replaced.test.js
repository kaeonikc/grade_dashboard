'use strict';
// A copy replaced by a renamed course (`grader split`: 2026_S2_Astro51_SEC_51 → 2026_S2_Astro, the old copy left on
// Drive): listCourses leaves it out, unless it still has edits not pulled; then it stays, marked `replaced_by`.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createGas, golden, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const G = '2569-2';

// F1 is the old copy, F2 the course renamed from it; both in grade_courses/2569-2 (a semester shortcut) or flat.
function setup(t, o = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-replaced-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const courses = { [H.F1]: { journal: o.journal }, [H.F2]: { course: { ...golden(H.F2), renamed_from: [H.F1] } } };
  if (o.flat) {
    for (const [f, opts] of Object.entries(courses)) layoutCourse(dir, f, opts);
    return gas;
  }
  const sem = path.join(dir, 'grade_courses', G);
  fs.mkdirSync(sem, { recursive: true });
  fs.mkdirSync(path.join(dir, 'grade_web'), { recursive: true });
  for (const [f, opts] of Object.entries(courses)) {
    fs.renameSync(layoutCourse(path.join(dir, 'tmp_' + f), f, opts), path.join(sem, f));
  }
  if (o.other) {  // a second group that holds a course with the old copy's name
    const other = path.join(dir, 'grade_courses', '2569-1');
    fs.mkdirSync(other, { recursive: true });
    fs.renameSync(layoutCourse(path.join(dir, 'tmp_other'), H.F1), path.join(other, H.F1));
    fs.symlinkSync(other, path.join(dir, 'grade_web', '2569-1'));
  }
  fs.symlinkSync(sem, path.join(dir, 'grade_web', G));
  return gas;
}

const listed = (gas) => {
  const r = gas.call('listCourses');
  assert.strictEqual(r.ok, true);
  return r;
};

test('the old copy of a renamed course leaves the list, and its group counts one course', (t) => {
  const r = listed(setup(t));
  assert.deepStrictEqual(r.courses.map((c) => c.folder), [G + '/' + H.F2]);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(r.groups)), [{ name: G, count: 1 }]);
});

test('outside a group the old name is matched bare', (t) => {
  const r = listed(setup(t, { flat: true }));
  assert.deepStrictEqual(r.courses.map((c) => c.folder), [H.F2]);
});

test('an old copy with edits not pulled stays, marked with the course that replaced it', (t) => {
  const r = listed(setup(t, { journal: 'three_unpulled.jsonl' }));
  const old = r.courses.find((c) => c.folder === G + '/' + H.F1);
  assert.ok(old, 'kept while it has unpulled edits');
  assert.strictEqual(old.unpulled, 3);
  assert.strictEqual(old.replaced_by, G + '/' + H.F2);
  assert.ok(!r.courses.find((c) => c.folder === G + '/' + H.F2).replaced_by);
});

test('a course of the same name in another group is not hidden', (t) => {
  const r = listed(setup(t, { other: true }));
  assert.deepStrictEqual(r.courses.map((c) => c.folder).sort(), ['2569-1/' + H.F1, G + '/' + H.F2].sort());
});
