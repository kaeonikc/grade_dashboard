'use strict';
// A failure of the page's own code is told apart from a google.script.run failure, so "Couldn't open …" names the
// error instead of "Google didn't answer" (the phone showed that while the server had answered).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const H = require('./helpers.js');

const SRC = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8').replace(/^<script>|<\/script>\s*$/g, '');

function page(fail) {
  const run = (ok, bad) => new Proxy({}, { get(_, k) {
    if (k === 'withSuccessHandler') return (f) => run(f, bad);
    if (k === 'withFailureHandler') return (f) => run(ok, f);
    return () => setImmediate(() => (fail ? bad(fail) : ok({ ok: true })));
  } });
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { get run() { return run(null, null); } } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {}, length: 0, key: () => null },
    performance: { now: () => 0 }, document: { dispatchEvent() {} }, window: { addEventListener() {} },
    navigator: { onLine: true }, Event: class { constructor(t) { this.type = t; } }, Error, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  return (code) => vm.runInContext(code, ctx);
}

test('a failed server call is not a page error', async () => {
  const js = page(new Error('NetworkError: Connection failure due to HTTP 0'));
  const err = await js('server')('loadCourse', 'x').then(() => null, (e) => e);
  assert.strictEqual(err.fromGoogle, true);
  assert.strictEqual(js('failureKind')(err), 'other');
});

test('an error thrown by the page itself is a page error', () => {
  const js = page(null);
  assert.strictEqual(js('failureKind')(new TypeError("undefined is not an object (evaluating 'x.y')")), 'page');
});
