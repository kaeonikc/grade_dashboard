'use strict';
// Semester groups (SPEC_semester_groups.md D3, D4): an item in grade_web that holds no course files is a group, and
// its course folders are listed under its name, with the path `<group>/<course>`. In the fake Drive a symlink is a
// shortcut: here grade_web/2569-1 points to grade_courses/2569-1.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const HW = 'data/' + H.P1 + '_homework.csv';
const G = '2569-1';
const plain = (v) => JSON.parse(JSON.stringify(v));

// F2 flat in grade_web; F1 and F3 in grade_courses/2569-1, which also holds a slides folder and a loose file.
function setup(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-groups-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  layoutCourse(dir, H.F2);
  const sem = path.join(dir, 'grade_courses', G);
  const folders = {};
  for (const f of [H.F1, H.F3]) {
    folders[f] = layoutCourse(path.join(dir, 'tmp_' + f), f);
    fs.mkdirSync(sem, { recursive: true });
    fs.renameSync(folders[f], path.join(sem, f));
    folders[f] = path.join(sem, f);
  }
  fs.mkdirSync(path.join(sem, 'slides'));
  fs.writeFileSync(path.join(sem, 'slides', 'week1.txt'), 'not a course');
  fs.writeFileSync(path.join(sem, 'notes.txt'), 'not a course');
  fs.symlinkSync(sem, path.join(dir, 'grade_web', G));
  t.after(() => {
    assert.ok(!/99\d{8,9}/.test(gas.logText()), 'logs hold a student ID');
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return { gas, dir, sem, folders };
}

const read = (folder, rel) => fs.readFileSync(path.join(folder, rel), 'utf8');

test('a semester shortcut lists its courses under the group; other folders in it are left out', (t) => {
  const { gas } = setup(t);
  gas.counts = {};
  const r = gas.call('listCourses');
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.courses.map((c) => [c.folder, c.group, c.available]),
    [[H.F2, null, true], [G + '/' + H.F1, G, true], [G + '/' + H.F3, G, true]]);
  assert.deepStrictEqual(plain(r.groups), [{ name: G, count: 2 }]);
  assert.strictEqual(r.courses[1].course_name, 'ฟิสิกส์จำลอง');
  // root, grade_web, its items, the group's subfolders, then the courses' data and course_info folders
  assert.ok(gas.counts['Files.list'] <= 5, 'listings: ' + gas.counts['Files.list']);
});

test('a course in a group opens, saves and undoes by its path', (t) => {
  const { gas, folders } = setup(t);
  const p = G + '/' + H.F1;
  const r = gas.call('loadCourse', p);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.folder, p);
  for (const f of r.course.files) assert.strictEqual(r.files[f], read(folders[H.F1], f), f);
  const hw0 = read(folders[H.F1], HW);
  const s = gas.call('saveBatch', p, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]);
  assert.strictEqual(s.saved.length, 1);
  assert.strictEqual(read(folders[H.F1], HW), hw0.replace('ทดสอบ,8,,,8', 'ทดสอบ,8,9,,8'));
  const u = gas.call('undoLastSave', p, s.batch);
  assert.strictEqual(u.ok, true);
  assert.strictEqual(read(folders[H.F1], HW), hw0);
  assert.strictEqual(gas.call('loadCourse', p).journal.unpulled, 2);
});

test('only <course> and <group>/<course> are course paths', (t) => {
  const { gas } = setup(t);
  for (const p of [G, H.F1, H.F2 + '/data', G + '/slides', G + '/' + H.F1 + '/data', 'nope/' + H.F1]) {
    const r = gas.call('loadCourse', p);
    assert.deepStrictEqual([r.ok, r.code], [false, 'NOT_FOUND'], p);
  }
  assert.strictEqual(gas.call('loadCourse', H.F2).ok, true);
});

test('a group with no courses is listed with count 0; a course in it that lost course.json stays listed', (t) => {
  const { gas, dir, folders } = setup(t);
  fs.mkdirSync(path.join(dir, 'grade_courses', '2568-2', 'slides'), { recursive: true });
  fs.symlinkSync(path.join(dir, 'grade_courses', '2568-2'), path.join(dir, 'grade_web', '2568-2'));
  fs.rmSync(path.join(folders[H.F3], 'course.json'));
  const r = gas.call('listCourses');
  assert.deepStrictEqual(plain(r.groups), [{ name: '2568-2', count: 0 }, { name: G, count: 2 }]);
  const f3 = r.courses.find((c) => c.folder === G + '/' + H.F3);
  assert.deepStrictEqual([f3.available, f3.reason],
    [false, 'course.json is missing. Push the course again from the Mac: grader web-push']);
});

test('the pending marker of a course in a group is under its folder id', (t) => {
  const { gas, folders } = setup(t);
  const p = G + '/' + H.F1;
  const hw0 = read(folders[H.F1], HW);
  gas.failOn('setContent', 2);
  assert.throws(() => gas.call('saveBatch', p, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]));
  const id = vm.runInContext('coursesIn_(gradeWebFolder_())', gas.ctx).courses.find((c) => c.path === p).folder.id;
  assert.ok(('pending:' + id) in gas.props());
  gas.failOn('setContent', 0);
  assert.strictEqual(gas.call('listCourses').ok, true);
  assert.strictEqual(read(folders[H.F1], HW), hw0.replace('ทดสอบ,8,,,8', 'ทดสอบ,8,9,,8'), 'rolled forward');
});

test('a folder name with a / is unavailable rather than misread as a path', (t) => {
  const { gas } = setup(t);
  const list = gas.ctx.Drive.Files.list;
  gas.ctx.Drive.Files.list = (params) => {
    const reply = list(params);
    for (const f of reply.files) if (f.name === H.F2) f.name = 'a/b';
    return reply;
  };
  const r = gas.call('listCourses');
  assert.deepStrictEqual(plain(r.courses[0]), { folder: 'a/b', group: null, available: false,
    reason: 'The folder name has a / in it. Rename it in Drive, then reload.' });
  assert.strictEqual(gas.call('loadCourse', 'a/b').code, 'NOT_FOUND');
});
