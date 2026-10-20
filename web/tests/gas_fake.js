'use strict';
// Apps Script fakes for the server harness (web/SPEC.md "Layer 1b"). Test tooling only, never deployed.
//
// createGas({drive, propsFile, now, active, effective, seed}) loads every web/apps_script/*.js file into one
// node:vm context (the Apps Script global scope) with fakes for DriveApp and the Advanced Drive service's
// Drive.Files.list (over the `drive` directory, which stands for "My Drive"), PropertiesService and CacheService
// (both optionally persisted next to `propsFile`), LockService, Session, Utilities, HtmlService, MimeType, a fixed
// clock, captured console/Logger and failure injection.
//
// If drive.js needs a DriveApp method this fake lacks, add it here (tooling, not assertions).
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const APPS = path.resolve(__dirname, '..', 'apps_script');
const FIXTURES = path.join(__dirname, 'fixtures');
const GOLDEN = path.join(__dirname, 'golden');
const OWNER = 'teacher@example.test';
const DEFAULT_PUSH = 'p-20270119-201500';
const DEFAULT_PUSHED_AT = '2027-01-19T20:15:00+07:00';

function iterator(items) {
  let i = 0;
  return { hasNext: () => i < items.length, next: () => { if (i >= items.length) throw new Error('No more items'); return items[i++]; } };
}

// ---- dates: Utilities.formatDate with Java SimpleDateFormat patterns, time zones through Intl ----
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function zoneParts(ms, tz) {
  const zone = /^(GMT|UTC)$/i.test(tz) ? 'UTC' : tz;
  const f = new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric',
    day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric', weekday: 'short' });
  const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  const local = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  const offsetMin = Math.round((local - Math.floor(ms / 1000) * 1000) / 60000);
  return { y: +p.year, M: +p.month, d: +p.day, H: +p.hour, m: +p.minute, s: +p.second, S: ((ms % 1000) + 1000) % 1000,
    E: DAYS.indexOf(p.weekday), off: offsetMin };
}

function formatDate(date, tz, pattern) {
  const ms = date instanceof Date || (date && typeof date.getTime === 'function') ? date.getTime() : +date;
  const z = zoneParts(ms, tz || 'Asia/Bangkok');
  const pad = (n, w) => String(n).padStart(w, '0');
  const off = (sep) => {
    const sign = z.off < 0 ? '-' : '+';
    const a = Math.abs(z.off);
    return sign + pad(Math.floor(a / 60), 2) + sep + pad(a % 60, 2);
  };
  let out = '';
  for (let i = 0; i < pattern.length;) {
    const ch = pattern[i];
    if (ch === "'") {
      const j = pattern.indexOf("'", i + 1);
      out += j === i + 1 ? "'" : pattern.slice(i + 1, j < 0 ? undefined : j);
      i = j < 0 ? pattern.length : j + 1;
      continue;
    }
    let n = 1;
    while (pattern[i + n] === ch) n++;
    const tok = ch.repeat(n);
    switch (ch) {
      case 'y': out += n === 2 ? pad(z.y % 100, 2) : pad(z.y, n); break;
      case 'M': out += n >= 3 ? MONTHS[z.M - 1] : pad(z.M, n); break;
      case 'd': out += pad(z.d, n); break;
      case 'H': out += pad(z.H, n); break;
      case 'm': out += pad(z.m, n); break;
      case 's': out += pad(z.s, n); break;
      case 'S': out += pad(z.S, 3).slice(0, n); break;
      case 'E': out += DAYS[z.E]; break;
      case 'X': out += z.off === 0 && n < 4 ? 'Z' : (n === 1 ? off('').slice(0, 3) : off(n === 2 ? '' : ':')); break;
      case 'Z': out += off(''); break;
      default: out += tok;
    }
    i += n;
  }
  return out;
}

// ---- the fake ----
function createGas(opts = {}) {
  const driveDir = path.resolve(opts.drive);
  fs.mkdirSync(driveDir, { recursive: true });
  const gas = {
    driveDir,
    logs: [],
    access: [],           // {op: list|read|write|create|trash, path}
    lockEvents: [],       // 'acquire' | 'release' | 'timeout'
    lockTimeout: false,
    htmlRequests: [],     // template / file names asked of HtmlService
    failures: {},         // method -> call number that throws
    counts: {},
    users: { active: opts.active || OWNER, effective: opts.effective || OWNER },
    now: null,
  };

  // ScriptProperties, optionally persisted (gas_run.js runs one call per process)
  const propsFile = opts.propsFile ? path.resolve(opts.propsFile) : null;
  let scriptProps = {};
  if (propsFile && fs.existsSync(propsFile)) scriptProps = JSON.parse(fs.readFileSync(propsFile, 'utf8') || '{}');
  const persist = () => { if (propsFile) fs.writeFileSync(propsFile, JSON.stringify(scriptProps, null, 1)); };
  gas.props = () => Object.assign({}, scriptProps);
  function propertyStore(store, save) {
    return {
      getProperty: (k) => (Object.prototype.hasOwnProperty.call(store.v, k) ? store.v[k] : null),
      setProperty(k, v) { store.v[k] = String(v); save(); return this; },
      deleteProperty(k) { delete store.v[k]; save(); return this; },
      getProperties: () => Object.assign({}, store.v),
      getKeys: () => Object.keys(store.v),
      setProperties(o, deleteAllOthers) {
        if (deleteAllOthers) store.v = {};
        for (const [k, v] of Object.entries(o)) store.v[k] = String(v);
        save();
        return this;
      },
      deleteAllProperties() { store.v = {}; save(); return this; },
    };
  }
  const scriptStore = { get v() { return scriptProps; }, set v(x) { scriptProps = x; } };
  const userStore = { v: {} };

  const rel = (p) => path.relative(driveDir, p).split(path.sep).join('/');
  const log = (op, p) => gas.access.push({ op, path: rel(p) });
  function maybeFail(method) {
    gas.counts[method] = (gas.counts[method] || 0) + 1;
    if (gas.failures[method] === gas.counts[method]) throw new Error('Injected failure: ' + method + ' #' + gas.counts[method]);
  }
  gas.failOn = (method, n) => { gas.failures[method] = n; gas.counts[method] = 0; };

  // stable ids per path (never real Drive ids)
  const ids = new Map();
  const paths = new Map();
  const idOf = (p) => {
    if (!ids.has(p)) { const id = 'fake' + (ids.size + 1); ids.set(p, id); paths.set(id, p); }
    return ids.get(p);
  };

  function blob(bytes, name, contentType) {
    let buf = Buffer.from(bytes);
    let nm = name || null;
    return {
      getDataAsString: () => buf.toString('utf8'),          // a BOM stays as U+FEFF
      getBytes: () => Array.from(buf, (b) => (b > 127 ? b - 256 : b)),  // Java bytes are signed
      getContentType: () => contentType || 'application/octet-stream',
      getName: () => nm,
      setName(n) { nm = n; return this; },
      setDataFromString(s) { buf = Buffer.from(s, 'utf8'); return this; },
      copyBlob() { return blob(buf, nm, contentType); },
      __buf: () => buf,
    };
  }

  function File(p) {
    return {
      getId: () => idOf(p),
      getName: () => path.basename(p),
      getBlob() { log('read', p); maybeFail('getBlob'); return blob(fs.readFileSync(p), path.basename(p), 'text/plain'); },
      getAs(type) { return this.getBlob(); },
      setContent(text) {
        log('write', p);
        maybeFail('setContent');
        fs.writeFileSync(p, Buffer.from(String(text), 'utf8'));
        return this;
      },
      getSize: () => fs.statSync(p).size,
      getLastUpdated: () => new ctx.Date(fs.statSync(p).mtimeMs),
      getDateCreated: () => new ctx.Date(fs.statSync(p).birthtimeMs),
      getMimeType: () => (p.endsWith('.csv') ? 'text/csv' : p.endsWith('.json') ? 'application/json' : 'text/plain'),
      isTrashed: () => !fs.existsSync(p),
      setTrashed(v) { if (v) { log('trash', p); fs.rmSync(p, { force: true }); } return this; },
      getParents: () => iterator([Folder(path.dirname(p))]),
      getUrl: () => 'https://drive.example.test/' + idOf(p),
    };
  }

  function Folder(p) {
    const children = (dirs) => {
      log('list', p);
      return fs.readdirSync(p, { withFileTypes: true })
        .filter((e) => (dirs ? e.isDirectory() : e.isFile()))
        .map((e) => e.name).sort()
        .map((n) => (dirs ? Folder(path.join(p, n)) : File(path.join(p, n))));
    };
    return {
      getId: () => idOf(p),
      getName: () => (p === driveDir ? 'My Drive' : path.basename(p)),
      getFolders: () => iterator(children(true)),
      getFoldersByName: (name) => iterator(children(true).filter((f) => f.getName() === name)),
      getFiles: () => iterator(children(false)),
      getFilesByName: (name) => iterator(children(false).filter((f) => f.getName() === name)),
      getFilesByType: (mime) => iterator(children(false).filter((f) => f.getMimeType() === mime)),
      createFolder(name) { const q = path.join(p, name); fs.mkdirSync(q, { recursive: true }); return Folder(q); },
      createFile(name, content, mime) {
        let data;
        if (name && typeof name === 'object' && name.__buf) { data = name.__buf(); name = name.getName(); }
        else data = Buffer.from(content == null ? '' : String(content), 'utf8');
        const q = path.join(p, name);
        log('create', q);
        maybeFail('createFile');
        fs.writeFileSync(q, data);
        return File(q);
      },
      getParents: () => iterator(p === driveDir ? [] : [Folder(path.dirname(p))]),
      isTrashed: () => !fs.existsSync(p),
      setTrashed(v) { if (v) { log('trash', p); fs.rmSync(p, { recursive: true, force: true }); } return this; },
      getLastUpdated: () => new ctx.Date(fs.statSync(p).mtimeMs),
      getUrl: () => 'https://drive.example.test/' + idOf(p),
    };
  }

  function walk(dir, wantDirs, name) {
    const out = [];
    for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
      const q = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (wantDirs && e.name === name) out.push(Folder(q));
        out.push(...walk(q, wantDirs, name));
      } else if (!wantDirs && e.name === name) out.push(File(q));
    }
    return out;
  }

  // The Advanced Drive service (v3), as drive.js uses it: Files.list over `'<id>' in parents` (or-joined),
  // `name = '…'`, `mimeType = '…'` and `trashed = false` (trashed items are deleted here, so always true).
  // `gas.pageSize` forces small pages to exercise page tokens.
  const FOLDER_MIME = 'application/vnd.google-apps.folder';
  const Drive = {
    Files: {
      list(params) {
        maybeFail('Files.list');
        const q = String(params.q || '');
        const parents = Array.from(q.matchAll(/'([^']+)' in parents/g), (m) => m[1]);
        const nameM = /\bname = '((?:[^'\\]|\\.)*)'/.exec(q);
        const mimeM = /\bmimeType = '([^']+)'/.exec(q);
        const items = [];
        for (const pid of parents) {
          const dir = pid === 'root' ? driveDir : paths.get(pid);
          if (!dir || !fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) continue;
          log('list', dir);
          for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
            const p = path.join(dir, e.name);
            const folder = e.isDirectory();
            const item = { id: idOf(p), name: e.name, mimeType: folder ? FOLDER_MIME : File(p).getMimeType(),
              parents: [idOf(dir)] };
            if (!folder) item.md5Checksum = crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex');
            if (nameM && e.name !== nameM[1].replace(/\\(.)/g, '$1')) continue;
            if (mimeM && item.mimeType !== mimeM[1]) continue;
            items.push(item);
          }
        }
        const size = gas.pageSize || params.pageSize || 100;
        const start = +(params.pageToken || 0);
        const reply = { files: items.slice(start, start + size) };
        if (start + size < items.length) reply.nextPageToken = String(start + size);
        return reply;
      },
    },
  };

  // CacheService's script cache: values over 100 KB are refused like the real one; expiry is not modelled.
  const cacheFile = propsFile ? propsFile + '.cache' : null;
  const cacheStore = new Map(cacheFile && fs.existsSync(cacheFile) ? Object.entries(JSON.parse(fs.readFileSync(cacheFile, 'utf8') || '{}')) : []);
  const saveCache = () => { if (cacheFile) fs.writeFileSync(cacheFile, JSON.stringify(Object.fromEntries(cacheStore))); };
  const putOne = (k, v) => {
    if (String(k).length > 250) throw new Error('Argument too large: key');
    if (Buffer.byteLength(String(v), 'utf8') > 100 * 1024) throw new Error('Argument too large: value');
    cacheStore.set(String(k), String(v));
  };
  const scriptCache = {
    get(k) { maybeFail('Cache.get'); return cacheStore.has(k) ? cacheStore.get(k) : null; },
    getAll(keys) {
      maybeFail('Cache.getAll');
      const o = {};
      for (const k of keys) if (cacheStore.has(k)) o[k] = cacheStore.get(k);
      return o;
    },
    put(k, v) { maybeFail('Cache.put'); putOne(k, v); saveCache(); },
    putAll(values) { maybeFail('Cache.putAll'); for (const [k, v] of Object.entries(values)) putOne(k, v); saveCache(); },
    remove(k) { cacheStore.delete(k); saveCache(); },
    removeAll(keys) { for (const k of keys) cacheStore.delete(k); saveCache(); },
  };
  gas.cache = cacheStore;
  gas.evictCache = () => { cacheStore.clear(); saveCache(); };

  const DriveApp = {
    getRootFolder: () => Folder(driveDir),
    getFolderById(id) { const p = paths.get(id); if (!p || !fs.existsSync(p)) throw new Error('No item with the given ID could be found.'); return Folder(p); },
    getFileById(id) { const p = paths.get(id); if (!p || !fs.existsSync(p)) throw new Error('No item with the given ID could be found.'); return File(p); },
    getFoldersByName: (name) => iterator(walk(driveDir, true, name)),
    getFilesByName: (name) => iterator(walk(driveDir, false, name)),
    createFolder: (name) => Folder(driveDir).createFolder(name),
    createFile: (name, content, mime) => Folder(driveDir).createFile(name, content, mime),
  };

  let lockHeld = false;
  const lock = {
    waitLock() {
      if (gas.lockTimeout) { gas.lockEvents.push('timeout'); throw new Error('Lock timeout: another process was holding the lock for too long.'); }
      if (lockHeld) throw new Error('Fake lock: waitLock while already held by this execution');
      lockHeld = true;
      gas.lockEvents.push('acquire');
    },
    tryLock() {
      if (gas.lockTimeout) { gas.lockEvents.push('timeout'); return false; }
      lockHeld = true;
      gas.lockEvents.push('acquire');
      return true;
    },
    releaseLock() { if (lockHeld) { lockHeld = false; gas.lockEvents.push('release'); } },
    hasLock: () => lockHeld,
  };

  // seeded randomness
  let seed = opts.seed == null ? 1 : opts.seed;
  const nextBytes = (n) => {
    const h = crypto.createHash('sha256').update('gas-fake:' + seed++).digest();
    return h.subarray(0, n);
  };
  const rand = () => nextBytes(4).readUInt32BE(0) / 4294967296;

  function htmlOutput(content) {
    const meta = [];
    let title = '';
    let body = content || '';
    return {
      getContent: () => body,
      setContent(c) { body = String(c); return this; },
      append(c) { body += String(c); return this; },
      appendUntrusted(c) { body += String(c).replace(/&/g, '&amp;').replace(/</g, '&lt;'); return this; },
      setTitle(t) { title = String(t); return this; },
      getTitle: () => title,
      addMetaTag(name, c) { meta.push({ name, content: c }); return this; },
      getMetaTags: () => meta.map((m) => ({ getName: () => m.name, getContent: () => m.content })),
      setXFrameOptionsMode() { return this; },
      setSandboxMode() { return this; },
      setFaviconUrl() { return this; },
      setWidth() { return this; },
      setHeight() { return this; },
      __meta: meta,
    };
  }
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  function compileTemplate(src) {
    let code = 'var __out = "";\n';
    const re = /<\?(!?=)?([\s\S]*?)\?>/g;
    let last = 0;
    let m;
    while ((m = re.exec(src))) {
      code += '__out += ' + JSON.stringify(src.slice(last, m.index)) + ';\n';
      if (m[1] === '=') code += '__out += __esc(' + m[2] + ');\n';
      else if (m[1] === '!=') code += '__out += (' + m[2] + ');\n';
      else code += m[2] + '\n';
      last = re.lastIndex;
    }
    code += '__out += ' + JSON.stringify(src.slice(last)) + ';\nreturn __out;';
    return vm.runInContext('(function(__vars, __esc){ with (__vars) {\n' + code + '\n} })', ctx);
  }
  function template(src) {
    const t = {
      evaluate() {
        const vars = {};
        for (const k of Object.keys(t)) if (typeof t[k] !== 'function') vars[k] = t[k];
        return htmlOutput(compileTemplate(src)(vars, esc));
      },
      getRawContent: () => src,
      getCode: () => src,
    };
    return t;
  }
  const readHtml = (name) => {
    gas.htmlRequests.push(name);
    return fs.readFileSync(path.join(APPS, name.endsWith('.html') ? name : name + '.html'), 'utf8');
  };
  const HtmlService = {
    createTemplateFromFile: (name) => template(readHtml(name)),
    createTemplate: (src) => template(typeof src === 'string' ? src : src.getDataAsString()),
    createHtmlOutputFromFile: (name) => htmlOutput(readHtml(name)),
    createHtmlOutput: (c) => htmlOutput(c == null ? '' : typeof c === 'string' ? c : c.getDataAsString()),
    XFrameOptionsMode: { ALLOWALL: 'ALLOWALL', DEFAULT: 'DEFAULT' },
    SandboxMode: { IFRAME: 'IFRAME', NATIVE: 'NATIVE', EMULATED: 'EMULATED' },
  };

  const capture = (level) => (...a) => gas.logs.push({ level, text: a.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ') });
  const sandbox = {
    DriveApp,
    Drive,
    CacheService: { getScriptCache: () => scriptCache, getUserCache: () => scriptCache, getDocumentCache: () => null },
    PropertiesService: {
      getScriptProperties: () => propertyStore(scriptStore, persist),
      getUserProperties: () => propertyStore(userStore, () => {}),
      getDocumentProperties: () => null,
    },
    LockService: { getScriptLock: () => lock, getUserLock: () => lock, getDocumentLock: () => null },
    Session: {
      getActiveUser: () => ({ getEmail: () => gas.users.active }),
      getEffectiveUser: () => ({ getEmail: () => gas.users.effective }),
      getScriptTimeZone: () => 'Asia/Bangkok',
      getTemporaryActiveUserKey: () => 'temp-key',
    },
    Utilities: {
      formatDate,
      getUuid: () => {
        const b = Buffer.from(nextBytes(16));
        b[6] = (b[6] & 0x0f) | 0x40;
        b[8] = (b[8] & 0x3f) | 0x80;
        const h = b.toString('hex');
        return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
      },
      sleep: () => {},
      newBlob: (data, type, name) => blob(typeof data === 'string' ? Buffer.from(data, 'utf8') : Buffer.from(data.map((x) => x & 0xff)), name, type),
      computeDigest: (alg, value) => Array.from(crypto.createHash(String(alg).toLowerCase().replace('_', '')).update(value).digest(), (x) => (x > 127 ? x - 256 : x)),
      base64Encode: (d) => Buffer.from(typeof d === 'string' ? d : d.map((x) => x & 0xff)).toString('base64'),
      DigestAlgorithm: { SHA_256: 'SHA_256', MD5: 'MD5', SHA_1: 'SHA_1' },
      Charset: { UTF_8: 'UTF-8' },
    },
    HtmlService,
    MimeType: new Proxy({ CSV: 'text/csv', PLAIN_TEXT: 'text/plain', HTML: 'text/html', JSON: 'application/json' },
      { get: (o, k) => (k in o ? o[k] : String(k)) }),
    ContentService: {
      createTextOutput: (s) => ({ getContent: () => s, setMimeType() { return this; } }),
      MimeType: { JSON: 'JSON', TEXT: 'TEXT' },
    },
    console: { log: capture('log'), info: capture('info'), warn: capture('warn'), error: capture('error') },
    Logger: { log: (...a) => { capture('Logger')(...a); return sandbox.Logger; } },
  };
  const ctx = vm.createContext(sandbox);
  gas.ctx = ctx;
  vm.runInContext(`(function(){
    const RealDate = Date; let fixed = null;
    class FakeDate extends RealDate {
      constructor(...a) { if (a.length === 0 && fixed !== null) super(fixed); else super(...a); }
      static now() { return fixed !== null ? fixed : RealDate.now(); }
    }
    globalThis.Date = FakeDate;
    globalThis.__setNow = (ms) => { fixed = ms; };
  })();`, ctx);
  ctx.__rand = rand;
  vm.runInContext('Math.random = __rand; delete globalThis.__rand;', ctx);

  gas.setNow = (iso) => { gas.now = iso; ctx.__setNow(iso == null ? null : Date.parse(iso)); };
  gas.setUser = (active, effective) => { gas.users = { active, effective: effective || OWNER }; };
  gas.setNow(opts.now || null);

  // load the real server files, as Apps Script would (one global scope)
  if (!fs.existsSync(APPS)) throw new Error('web/apps_script/ is missing');
  for (const f of fs.readdirSync(APPS).filter((n) => n.endsWith('.js')).sort()) {
    vm.runInContext(fs.readFileSync(path.join(APPS, f), 'utf8'), ctx, { filename: path.join(APPS, f) });
  }

  // google.script.run semantics: arguments and replies cross as JSON
  gas.call = (name, ...args) => {
    const fn = vm.runInContext('(function(n, a){ var f = globalThis[n]; if (typeof f !== "function") ' +
      'throw new ReferenceError(n + " is not defined"); var r = f.apply(null, JSON.parse(a)); ' +
      'return r === undefined ? undefined : JSON.stringify(r); })', ctx);
    let out;
    try {
      out = fn(name, JSON.stringify(args));
    } finally {
      // the execution ends: Apps Script frees a lock the script still holds (recorded apart from 'release')
      if (lockHeld) { lockHeld = false; gas.lockEvents.push('auto-release'); }
    }
    return out === undefined ? undefined : JSON.parse(out);
  };
  gas.doGet = (e) => {
    const out = vm.runInContext('doGet', ctx)(e || { parameter: {} });
    return { content: out.getContent(), title: out.getTitle(), meta: out.__meta || [] };
  };
  gas.logText = () => gas.logs.map((l) => l.text).join('\n');
  return gas;
}

// ---- Drive layout as web-push leaves it (course.json from the golden file make_golden.py writes) ----
function golden(fixture) {
  return JSON.parse(fs.readFileSync(path.join(GOLDEN, fixture + '.json'), 'utf8')).course;
}

function layoutCourse(driveDir, fixture, o = {}) {
  const course = o.course || golden(fixture);
  const dest = path.join(driveDir, 'grade_web', fixture);
  fs.mkdirSync(dest, { recursive: true });
  const src = path.join(FIXTURES, fixture);
  for (const f of [course.roster].concat(course.files)) {
    fs.mkdirSync(path.dirname(path.join(dest, f)), { recursive: true });
    fs.copyFileSync(path.join(src, f), path.join(dest, f));
  }
  fs.writeFileSync(path.join(dest, 'course.json'), JSON.stringify(course, null, 1));
  const push = {
    format: 1, push_id: o.push || DEFAULT_PUSH, pushed_at: o.pushed_at || DEFAULT_PUSHED_AT,
    course_id: course.course_id, course_name: course.course_name, term: course.term, mac_folder: fixture,
    tool: 'grader web-push', files: ['course.json', course.roster].concat(course.files),
  };
  fs.writeFileSync(path.join(dest, 'push.json'), JSON.stringify(push));
  const journal = o.journal ? fs.readFileSync(path.join(FIXTURES, 'journals', o.journal)) : Buffer.alloc(0);
  fs.writeFileSync(path.join(dest, 'web_edits.jsonl'), journal);
  for (const [i, a] of (o.archives || []).entries()) {
    fs.mkdirSync(path.join(dest, 'archive'), { recursive: true });
    fs.copyFileSync(path.join(FIXTURES, 'journals', a), path.join(dest, 'archive', 'web_edits_20270121-18000' + i + '.jsonl'));
  }
  return dest;
}

module.exports = { createGas, layoutCourse, formatDate, OWNER, DEFAULT_PUSH, DEFAULT_PUSHED_AT };
