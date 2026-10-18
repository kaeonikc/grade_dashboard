# ADR 004: One source file per pure JS module, shared by node tests, the Apps Script server and the browser, with no build step

Date: 2026-10-18 · Status: accepted

## Context
The same logic runs in three places. The browser computes grades and checks typed input. The Apps Script server
conflict-checks and splices CSV cells. `node --test` checks both against golden files. Apps Script V8 has no
modules: every `.gs` file shares one global scope. HtmlService can only include `.html` files. Node needs
`module.exports`. Keeping two copies (one `.gs`, one `<script>`) would let them drift. A bundler would add npm
dev dependencies and a build step that the paste-in fallback (S13.2) would also need.

## Decision
Each pure module (`csv.js`, `grades.js`, `journal.js`, `save.js` in `web/apps_script/`) is **one factory function
declaration** with a CommonJS footer:

```js
function gwGrades() {
  'use strict';
  // ... no globals, no Apps Script or DOM APIs ...
  return { classify, sameCell, validateTyped, computeGrades /* ... */ };
}
if (typeof module !== 'undefined') module.exports = gwGrades;
```

- **Node tests:** `const Grades = require('../apps_script/grades.js')();`, run with `node --test 'web/tests/*.test.js'`.
  The server harness (`web/tests/gas_fake.js`) also loads every `apps_script/*.js` file into one `node:vm` context, so
  the non-pure server files are tested as Apps Script would load them.
- **Server:** clasp pushes the file as `grades.gs`. `Code.js` instantiates the modules lazily, in a `core_()`
  getter called inside request handlers (never at file top level, because file load order isn't guaranteed).
  Factories that need others take them as arguments (`gwSave(Csv, Grades)`).
- **Browser:** `Index.html` is a template. `<?!= clientCore_() ?>` emits `gwCsv.toString()`,
  `gwGrades.toString()` and `gwJournal.toString()` (journal summaries and the message formatters) plus the
  instantiation lines inside a `<script>`. `Function.prototype.toString` returns the
  exact source text (ES2019), so the browser runs byte-for-byte the code the tests ran.

## Alternatives considered
| Option | Why not |
|---|---|
| Duplicate the code in a `.gs` and an `.html` file | Two copies drift. The golden tests would cover only one of them |
| esbuild/rollup bundle + clasp | npm dev deps, a `dist/` step, and the paste-in fallback would have to paste build output |
| Serve the pure modules as `*.html` `<script>` files and test them by stripping tags in node | The tests would run a transformed file, and the server (which needs `csv.js`, `grades.js`, `save.js`) couldn't load an `.html` file |
| ES modules (`export`) | Apps Script V8 doesn't support `import`/`export` |

## Consequences
- No build: `clasp push` (or paste-in) sends exactly the files in `web/apps_script/`.
- Rule for these four files: no top-level code other than the factory declaration and the footer, no closures over
  globals, and no Apps Script/DOM calls. Otherwise `toString()` injection or node loading breaks. `node --test`
  loads every module in plain node, which catches most breaches.
- **Do not** add a bundler or split a module into a `.gs` and an `.html` copy "for clarity". That undoes this
  decision.
