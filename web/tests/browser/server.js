'use strict';
// Preview for the browser checks: the real page (through the fake's doGet) with google.script.run going to the real
// server code over a scratch copy of the Drive folder. node server.js DRIVE PORT [NOW]
const http = require('node:http');
const path = require('node:path');
const { createGas } = require(path.join(__dirname, '..', 'gas_fake.js'));

const [drive, port, now] = process.argv.slice(2);
const gas = createGas({ drive, propsFile: path.join(drive, 'props.json'), now: now || null });
const SHIM = `<script>
window.google = { script: { get run() {
  const make = (ok, bad) => new Proxy({}, { get(_, k) {
    if (k === 'withSuccessHandler') return (f) => make(f, bad);
    if (k === 'withFailureHandler') return (f) => make(ok, f);
    return (...args) => fetch('/call', { method: 'POST', body: JSON.stringify({ name: k, args }) })
      .then((r) => r.json()).then((r) => r.error ? bad && bad(new Error(r.error)) : ok && ok(r.reply));
  } });
  return make(null, null);
} } };
</script>`;
http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/call') {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      const { name, args } = JSON.parse(body);
      let out;
      try { out = { reply: gas.call(name, ...args) }; } catch (e) { out = { error: String((e && e.message) || e) }; }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify(out === undefined ? null : out));
    });
    return;
  }
  const page = gas.doGet({ parameter: {} });
  const html = page.content.replace('<head>',
    '<head><meta name="viewport" content="width=device-width, initial-scale=1">' + SHIM);
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
  res.end(html);
}).listen(+port, () => console.log('preview on ' + port));
