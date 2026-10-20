'use strict';
// Loading speed (SPEC_discard_and_speed.md D3-D5, "Targets"): batched Drive listings, the md5-keyed content cache,
// and fresh reads for every call that writes.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const HW = 'data/' + H.P1 + '_homework.csv';
const ALL = [H.F1, H.F2, H.F3, H.F4];

function setup(t, fixtures) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-speed-'));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  const folders = {};
  for (const f of fixtures) folders[f] = layoutCourse(dir, f);
  t.after(() => {
    assert.ok(!/99\d{8,9}/.test(gas.logText()), 'logs hold a student ID');
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return { gas, dir, folders };
}

// The reply plus what the call did: Drive listings, downloads (by path) and the reply's own counters.
function run(gas, name, ...args) {
  gas.counts = {};
  const n0 = gas.access.length;
  const reply = gas.call(name, ...args);
  const reads = gas.access.slice(n0).filter((a) => a.op === 'read').map((a) => a.path);
  return { reply, lists: gas.counts['Files.list'] || 0, reads, timing: reply.timing };
}

const read = (folder, rel) => fs.readFileSync(path.join(folder, rel), 'utf8');

test('listCourses lists 4 courses in at most 4 queries; warm, it downloads nothing', (t) => {
  const { gas } = setup(t, ALL);
  const cold = run(gas, 'listCourses');
  assert.strictEqual(cold.reply.courses.filter((c) => c.available).length, 4);
  assert.ok(cold.lists <= 4, 'listings: ' + cold.lists);
  assert.strictEqual(cold.reads.length, 12, 'course.json, push.json and the journal, once each');
  assert.deepStrictEqual([cold.timing.hit, cold.timing.miss, cold.timing.read], [0, 12, 12]);
  const warm = run(gas, 'listCourses');
  assert.deepStrictEqual(warm.reply.courses, cold.reply.courses);
  assert.ok(warm.lists <= 4);
  assert.deepStrictEqual(warm.reads, []);
  assert.deepStrictEqual([warm.timing.hit, warm.timing.miss], [12, 0]);
});

test('the number of queries does not grow with the courses (45 courses)', (t) => {
  const { gas, dir, folders } = setup(t, [H.F1]);
  for (let i = 0; i < 44; i++) fs.cpSync(folders[H.F1], path.join(dir, 'grade_web', 'copy_' + String(i).padStart(2, '0')), { recursive: true });
  const r = run(gas, 'listCourses');
  assert.strictEqual(r.reply.courses.length, 45);
  assert.ok(r.reply.courses.every((c) => c.available));
  // root, grade_web, the 45 course folders (2 queries of up to 40), their 90 data and course_info folders (3)
  assert.strictEqual(r.lists, 7);
});

test('loadCourse warm: at most 4 queries and no download; the bytes are the same', (t) => {
  const { gas, folders } = setup(t, [H.F1, H.F2]);
  const cold = run(gas, 'loadCourse', H.F1);
  assert.ok(cold.lists <= 4, 'listings: ' + cold.lists);
  const warm = run(gas, 'loadCourse', H.F1);
  assert.ok(warm.lists <= 4);
  assert.deepStrictEqual(warm.reads, []);
  for (const k of ['course', 'push', 'roster', 'files', 'journal']) assert.deepStrictEqual(warm.reply[k], cold.reply[k], k);
  for (const f of cold.reply.course.files) assert.strictEqual(warm.reply.files[f], read(folders[H.F1], f), f);
  const bom = run(gas, 'loadCourse', H.F2);
  const again = run(gas, 'loadCourse', H.F2).reply.files['data/9_กลศาสตร์ทดลอง_homework.csv'];
  assert.strictEqual(again, bom.reply.files['data/9_กลศาสตร์ทดลอง_homework.csv']);
  assert.ok(again.startsWith('﻿Student ID,') && again.includes('\r\n'), 'BOM and CRLF survive the cache');
});

test('a file changed on Drive is never served from the cache', (t) => {
  const { gas, folders } = setup(t, [H.F1]);
  run(gas, 'loadCourse', H.F1);
  const changed = read(folders[H.F1], HW).replace('ทดสอบ,8,,,8', 'ทดสอบ,8,6,,14');
  fs.writeFileSync(path.join(folders[H.F1], HW), changed);
  const r = run(gas, 'loadCourse', H.F1);
  assert.strictEqual(r.reply.files[HW], changed);
  assert.deepStrictEqual(r.reads.map((p) => p.split('/').slice(2).join('/')), [HW]);
});

test('saveBatch reads its CSV and the journal fresh even when cached, and caches what it wrote', (t) => {
  const { gas, folders } = setup(t, [H.F1]);
  run(gas, 'loadCourse', H.F1);
  const s = run(gas, 'saveBatch', H.F1, [{ student_id: '9900000001', column: 'hw2', value: '9', original: '' }]);
  assert.strictEqual(s.reply.saved.length, 1);
  const rel = (p) => p.split('/').slice(2).join('/');
  for (const f of ['course.json', 'push.json', 'web_edits.jsonl', HW]) assert.ok(s.reads.map(rel).includes(f), f + ' read fresh');
  assert.strictEqual(s.timing.hit, 0);
  assert.ok(s.lists <= 4);
  const r = run(gas, 'loadCourse', H.F1);
  assert.deepStrictEqual(r.reads, [], 'what the save wrote is cached under its new md5');
  assert.strictEqual(r.reply.files[HW], read(folders[H.F1], HW));
  assert.strictEqual(r.reply.journal.unpulled, 1);
});

test('page tokens are followed', (t) => {
  const { gas } = setup(t, ALL);
  const big = run(gas, 'listCourses').reply;
  gas.evictCache();
  gas.pageSize = 2;
  const r = run(gas, 'listCourses');
  assert.deepStrictEqual(r.reply.courses, big.courses);
  assert.ok(r.lists > 4);
  assert.strictEqual(run(gas, 'loadCourse', H.F1).reply.ok, true);
});

test('a file over one cache value is chunked and comes back whole', (t) => {
  const { gas, folders } = setup(t, [H.F1]);
  const extra = Array.from({ length: 1500 }, (_, i) => 'x' + i + ',นายยาวมาก ทดสอบทดสอบทดสอบทดสอบ,,,').join('\n') + '\n';
  const text = read(folders[H.F1], HW) + extra;
  fs.writeFileSync(path.join(folders[H.F1], HW), text);
  assert.ok(Buffer.byteLength(text) > 100 * 1024, 'bigger than one cache value');
  run(gas, 'loadCourse', H.F1);
  const r = run(gas, 'loadCourse', H.F1);
  assert.deepStrictEqual(r.reads, []);
  assert.strictEqual(r.reply.files[HW], text);
  // a lost chunk is a miss, never a partial text
  const key = [...gas.cache.keys()].find((k) => /:\d+$/.test(k));
  gas.cache.delete(key);
  const again = run(gas, 'loadCourse', H.F1);
  assert.strictEqual(again.reply.files[HW], text);
  assert.strictEqual(again.reads.length, 1);
});

test('a failing cache only costs downloads', (t) => {
  const { gas } = setup(t, [H.F1]);
  run(gas, 'loadCourse', H.F1);
  gas.failOn('Cache.getAll', 1);  // the first lookup: course.json and push.json
  const r = run(gas, 'loadCourse', H.F1);
  assert.strictEqual(r.reply.ok, true);
  assert.deepStrictEqual(r.reads.map((p) => path.basename(p)), ['course.json', 'push.json']);
  gas.failOn('Cache.getAll', 0);
  gas.failOn('Cache.putAll', 1);
  gas.evictCache();
  assert.strictEqual(run(gas, 'loadCourse', H.F1).reply.ok, true);
  assert.match(gas.logText(), /^cache_error get$/m);
  assert.match(gas.logText(), /^cache_error put$/m);
});
