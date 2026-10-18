'use strict';
// Course availability and trim details behind listCourses/loadCourse (web/SPEC.md "Course availability", "Trim").
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

function setup(t, o) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-avail-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T10:00:00+07:00' });
  const folder = layoutCourse(dir, H.F1, o || {});
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return { gas, folder };
}

const reason = (gas) => gas.call('listCourses').courses[0].reason;

test('a duplicate data file is named with its folder', (t) => {
  const { gas, folder } = setup(t);
  fs.writeFileSync(path.join(folder, 'data', H.P1 + '_homework (1).csv'), '');
  assert.strictEqual(reason(gas), 'Drive has duplicate files: data/' + H.P1 + '_homework (1).csv. ' +
    'See the README, "Duplicate files", then reload.');
});

test('a missing listed file makes the course unavailable', (t) => {
  const { gas, folder } = setup(t);
  fs.rmSync(path.join(folder, 'data', H.P1 + '_midterm.csv'));
  assert.strictEqual(reason(gas),
    'data/' + H.P1 + '_midterm.csv is missing. Push the course again from the Mac: grader web-push');
});

test('a damaged course.json or a missing push.json makes the course unavailable', (t) => {
  const { gas, folder } = setup(t);
  fs.writeFileSync(path.join(folder, 'course.json'), '{"format": 1,');
  assert.strictEqual(reason(gas),
    'course.json is damaged (not valid JSON). Push the course again from the Mac: grader web-push');
  layoutCourse(gas.driveDir, H.F1);
  fs.rmSync(path.join(folder, 'push.json'));
  assert.strictEqual(reason(gas), 'push.json is missing. Push the course again from the Mac: grader web-push');
});

test('a journal repaired by hand is trimmed again against every archive', (t) => {
  const { gas, folder } = setup(t, { journal: 'seven_lines.jsonl', archives: ['archive_pull_4.jsonl'] });
  const journal = path.join(folder, 'web_edits.jsonl');
  const seven = H.journalLines('seven_lines.jsonl');
  assert.strictEqual(gas.call('loadCourse', H.F1).journal.unpulled, 3);
  // The copy Drive made still holds a pulled line; the teacher merges it back while the course is unavailable.
  fs.writeFileSync(path.join(folder, 'web_edits (1).jsonl'), seven[0] + '\n');
  assert.strictEqual(gas.call('listCourses').courses[0].available, false);
  fs.writeFileSync(journal, [seven[0]].concat(seven.slice(4)).join('\n') + '\n');
  fs.rmSync(path.join(folder, 'web_edits (1).jsonl'));
  const c = gas.call('listCourses').courses[0];
  assert.strictEqual(c.unpulled, 3);
  assert.strictEqual(fs.readFileSync(journal, 'utf8'), seven.slice(4).join('\n') + '\n');
});

test('a discarded archive is not a pull', (t) => {
  const { gas, folder } = setup(t);
  fs.mkdirSync(path.join(folder, 'archive'));
  fs.writeFileSync(path.join(folder, 'archive', 'web_edits_20270121-180000_discarded.jsonl'),
    JSON.stringify({ kind: 'discarded', push: H.PUSH }) + '\n');
  assert.strictEqual(gas.call('loadCourse', H.F1).journal.undo_note, 'Nothing to undo');
});
