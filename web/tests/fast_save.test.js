'use strict';
// Save in the background (SPEC_fast_save.md): the page stays usable, and an edit made during a save is never lost.
// client_state.html runs in node:vm over a tmp Drive; a reply lands on the next tick, so what runs straight after
// saveEdits() happens during the save.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { createGas, layoutCourse } = require('./gas_fake.js');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');
const VIEWS = fs.readFileSync(path.join(H.APPS, 'client_views.html'), 'utf8');
const ONE = '9900000001';
const TWO = '9900000002';

async function open(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-fast-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const gas = createGas({ drive: dir, now: '2027-01-20T09:15:02+07:00' });
  layoutCourse(dir, H.F1);
  const run = (ok, fail) => new Proxy({}, { get(_, k) {
    if (k === 'withSuccessHandler') return (f) => run(f, fail);
    if (k === 'withFailureHandler') return (f) => run(ok, f);
    return (...args) => setImmediate(() => {
      let reply;
      try { reply = gas.call(k, ...args); } catch (e) { return fail(e); }
      ok(reply);
    });
  } });
  const stored = new Map();
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { get run() { return run(null, null); } } },
    localStorage: { getItem: (k) => (stored.has(k) ? stored.get(k) : null), setItem: (k, v) => stored.set(k, v),
      removeItem: (k) => stored.delete(k), length: 0, key: () => null },
    performance: { now: () => 0 }, document: { dispatchEvent() {} }, window: { addEventListener() {} },
    navigator: { onLine: true }, Event: class { constructor(type) { this.type = type; } }, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  await js('openCourse')(H.F1);
  const row = (id) => js('state.byId').get(id);
  const edit = (id) => js('state.edits').get(id + '\u0000hw2') || Array.from(js('state.edits').values())
    .find((e) => e.student_id === id && e.column === 'hw2');
  return { js, gas, stored, row, edit };
}

test('a background save leaves the cells open and the rest waiting', async (t) => {
  const { js, row } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  assert.strictEqual(js('state.sending').size, 1);
  assert.strictEqual(js('busy()'), false, 'cells stay open');
  assert.strictEqual(js('locked()'), true, 'Save, Discard, Undo, Reload wait');
  await p;
  assert.strictEqual(js('state.sending'), null);
  assert.strictEqual(js('locked()'), false);
  assert.strictEqual(js('state.edits').size, 0);
});

test('a save that waits, an Undo and a Drive check close the cells', async (t) => {
  const { js, row } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')();
  assert.strictEqual(js('state.sending'), null);
  assert.strictEqual(js('busy()'), true, 'Save and leave waits');
  await p;
  js('state').saving = true;
  assert.strictEqual(js('busy()'), true, 'Undo');
  js('state').saving = false;
  js('state').checking = true;
  assert.strictEqual(js('busy()'), true, 'Drive check');
});

test('an edit in another cell during a save stays unsaved', async (t) => {
  const { js, row, edit } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  js('setCell')(row(TWO), 'hw2', '6');
  await p;
  assert.strictEqual(edit(ONE), undefined, 'the sent cell left the list');
  assert.strictEqual(edit(TWO).value, '6');
  assert.strictEqual(js('state.edits').size, 1);
});

test('a cell changed again during its save keeps the newer value', async (t) => {
  const { js, row, edit } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  js('setCell')(row(ONE), 'hw2', '7');
  await p;
  assert.strictEqual(edit(ONE).value, '7');
  assert.strictEqual(edit(ONE).original, '5', 'its start value is what Drive now holds');
  assert.strictEqual(js('cellValue')(row(ONE), 'hw2'), '7');
  await js('saveEdits')(true);
  assert.strictEqual(js('state.edits').size, 0);
  assert.strictEqual(js('savedValue')(row(ONE), 'hw2'), '7', 'the next Save writes it');
});

test('a cell put back to its old value during its save stays an edit', async (t) => {
  const { js, row, edit } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  js('setCell')(row(ONE), 'hw2', '');
  await p;
  assert.strictEqual(edit(ONE).value, '', 'blank again');
  assert.strictEqual(edit(ONE).original, '5');
});

test('a cell changed and changed back during its save leaves the list', async (t) => {
  const { js, row, edit } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  js('setCell')(row(ONE), 'hw2', '7');
  js('setCell')(row(ONE), 'hw2', '5');
  assert.ok(edit(ONE), 'kept until the reply, in case the save fails');
  await p;
  assert.strictEqual(edit(ONE), undefined);
  assert.strictEqual(js('savedValue')(row(ONE), 'hw2'), '5');
});

test('a failed save keeps every edit, in the page and in the draft', async (t) => {
  const { js, gas, row, edit, stored } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  gas.failOn('setContent', 1);
  const p = js('saveEdits')(true);
  js('setCell')(row(TWO), 'hw2', '6');
  await assert.rejects(p);
  assert.strictEqual(js('state.sending'), null);
  assert.strictEqual(js('locked()'), false);
  assert.strictEqual(edit(ONE).value, '5');
  assert.strictEqual(edit(TWO).value, '6');
  const draft = Array.from(stored.entries()).find(([k]) => k.includes('draft'));
  assert.strictEqual(JSON.parse(draft[1]).edits.length, 2);
});

test('the draft stays until the reply, for a tab closed mid-save', async (t) => {
  const { js, row, stored } = await open(t);
  js('setCell')(row(ONE), 'hw2', '5');
  const p = js('saveEdits')(true);
  assert.ok(Array.from(stored.keys()).some((k) => k.includes('draft')));
  await p;
  assert.ok(!Array.from(stored.keys()).some((k) => k.includes('draft')));
});

test('the reply repaints in place; only Save and leave redraws', () => {
  assert.match(VIEWS, /if \(after\) renderView\(\); else refreshSaved\(reply\);/);
  assert.match(VIEWS, /saveEdits\(!after\)/);
});

test('the cells follow busy(), the rest stays on locked()', () => {
  assert.match(VIEWS, /cm\.fill\.disabled = busy\(\)/);
  assert.match(VIEWS, /kind === 'score' && !busy\(\)\) editCell/);
  assert.match(VIEWS, /function openPicker\(r, c\) \{\n  if \(busy\(\)\) return;/);
  assert.match(VIEWS, /function editSet\(value, thenNext\) \{\n  const \{ r, c, input \} = tb\.edit;\n  if \(busy\(\)\) return;/);
  assert.match(VIEWS, /function barSet[\s\S]*?if \(!it \|\| busy\(\)\) return;/);
  assert.match(VIEWS, /function openFill\(\) \{[\s\S]*?if \(!col \|\| busy\(\)\) return;/);
  assert.match(VIEWS, /function openSaveSheet\(\) \{\n  if \(!state\.edits\.size \|\| locked\(\)\) return;/);
  assert.match(VIEWS, /function leave\(then\) \{\n  if \(state\.sending\)/);
});
