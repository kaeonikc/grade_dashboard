'use strict';
// A course added to grade_web as a Drive shortcut to its folder (web/SPEC.md "Course availability"): the shortcut
// counts as the folder it points to, under the shortcut's name. In the fake Drive a symlink is a shortcut.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const HW = 'data/' + H.P1 + '_homework.csv';
const LINK = 'ฟิสิกส์ (shortcut)';

// F2 as a real folder in grade_web; F1 laid out elsewhere in My Drive, with a shortcut to it in grade_web.
function setup(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-shortcut-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  layoutCourse(dir, H.F2);
  const target = layoutCourse(path.join(dir, 'elsewhere'), H.F1);
  fs.symlinkSync(target, path.join(dir, 'grade_web', LINK));
  t.after(() => {
    assert.ok(!/99\d{8,9}/.test(gas.logText()), 'logs hold a student ID');
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return { gas, dir, target };
}

const read = (folder, rel) => fs.readFileSync(path.join(folder, rel), 'utf8');

test('a shortcut to a course folder is listed and opens under the shortcut name', (t) => {
  const { gas, target } = setup(t);
  const list = gas.call('listCourses');
  const c = list.courses.find((x) => x.folder === LINK);
  assert.ok(c, 'listed: ' + list.courses.map((x) => x.folder).join(', '));
  assert.deepStrictEqual([c.available, c.course_id], [true, JSON.parse(read(target, 'course.json')).course_id]);
  assert.strictEqual(list.courses.filter((x) => x.available).length, 2);
  const r = gas.call('loadCourse', LINK);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.folder, LINK);
  for (const f of r.course.files) assert.strictEqual(r.files[f], read(target, f), f);
});

test('a save through the shortcut writes the target folder, and its markers use the target id', (t) => {
  const { gas, target } = setup(t);
  const rec = vm.runInContext('subfolders_(gradeWebFolder_())', gas.ctx).find((r) => r.name === LINK);
  assert.strictEqual(gas.ctx.DriveApp.getFolderById(rec.id).getName(), H.F1, 'the record is the target folder');
  const hw0 = read(target, HW);
  gas.failOn('setContent', 2);  // the journal is written, the CSV is not: the pending marker stays
  assert.throws(() => gas.call('saveBatch', LINK, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]));
  assert.ok(('pending:' + rec.id) in gas.props(), 'pending marker under the target id');
  gas.failOn('setContent', 0);
  const r = gas.call('loadCourse', LINK);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(read(target, HW), hw0.replace('ทดสอบ,8,,,8', 'ทดสอบ,8,9,,8'));
  assert.strictEqual(r.files[HW], read(target, HW));
  assert.strictEqual(r.journal.unpulled, 1);
  assert.ok(!Object.keys(gas.props()).some((k) => k.startsWith('pending:')));
});

test('a shortcut whose target is gone is an empty group; a shortcut to a file is not a course', (t) => {
  const { gas, dir, target } = setup(t);
  fs.symlinkSync(path.join(dir, 'grade_web', H.F2, 'course.json'), path.join(dir, 'grade_web', 'a file shortcut'));
  fs.rmSync(target, { recursive: true });
  const list = gas.call('listCourses');
  assert.deepStrictEqual(list.courses.map((x) => x.folder), [H.F2]);
  assert.strictEqual(list.courses[0].available, true);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(list.groups)), [{ name: LINK, count: 0 }]);
  assert.strictEqual(gas.call('loadCourse', LINK).code, 'NOT_FOUND');
});

test('listings include shared drives, where a shortcut target may live', (t) => {
  const { gas } = setup(t);
  gas.call('listCourses');
  assert.ok(gas.listParams.length > 0);
  for (const p of gas.listParams) {
    assert.deepStrictEqual([p.supportsAllDrives, p.includeItemsFromAllDrives], [true, true]);
    assert.match(p.fields, /shortcutDetails\(targetId, targetMimeType\)/);
  }
});
