#!/usr/bin/env node
'use strict';
// node web/scripts/gas_run.js --drive DIR --props FILE [--now ISO] <function> [json-arg ...]
// Runs one real server function (web/apps_script/) through web/tests/gas_fake.js over a tmp Drive folder and prints
// its JSON reply on stdout. Used by web/scripts/e2e.sh. Test tooling only, never deployed.
const path = require('node:path');
const { createGas } = require(path.join(__dirname, '..', 'tests', 'gas_fake.js'));

function main(argv) {
  const opts = {};
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--drive' || argv[i] === '--props' || argv[i] === '--now') opts[argv[i].slice(2)] = argv[++i];
    else rest.push(argv[i]);
  }
  if (!opts.drive || !opts.props || rest.length === 0) {
    process.stderr.write('usage: gas_run.js --drive DIR --props FILE [--now ISO] <function> [json-arg ...]\n');
    return 2;
  }
  const [fn, ...raw] = rest;
  const args = raw.map((a) => { try { return JSON.parse(a); } catch (e) { return a; } });
  const gas = createGas({ drive: opts.drive, propsFile: opts.props, now: opts.now || null });
  const reply = gas.call(fn, ...args);
  process.stdout.write(JSON.stringify(reply === undefined ? null : reply) + '\n');
  return 0;
}

try {
  process.exitCode = main(process.argv.slice(2));
} catch (e) {
  process.stderr.write('gas_run: ' + (e && e.stack ? e.stack : e) + '\n');
  process.exitCode = 1;
}
