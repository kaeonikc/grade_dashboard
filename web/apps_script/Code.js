// grade_web server (Apps Script V8). Executes as the owner, access "Only myself".
// Logs hold only codes, byte counts and offsets: no names, IDs or scores.

const PAGE_TITLE = 'grade_web';
const JOURNAL = 'web_edits.jsonl';
const TOP_FILES = ['course.json', 'push.json', JOURNAL];
const LOCK_WAIT_MS = 25000;
const NOTE_NONE = 'Nothing to undo';
const NOTE_PULLED = 'Already pulled to the Mac; use `grader undo` there';
const UNDO_CHANGED = 'Another device saved since this page loaded. Reload to see the newest save, then try again.';
const CONFIG_STALE = 'Changed on another device after this page loaded. Nothing was saved.';
const ISO_FORMAT = "yyyy-MM-dd'T'HH:mm:ssXXX";
const DOGET_SLOT = '/*DOGET_MS*/null';  // in Index.html, replaced by doGet's time in ms

const NOT_AVAILABLE_HTML =
  '<h1>Not available</h1><p>This page opens only for the Google account that owns it.</p>';

// Unavailable reasons (Interface copy table, why.*).
const WHY = {
  noCourseJson: 'course.json is missing. Push the course again from the Mac: grader web-push',
  noPushJson: 'push.json is missing. Push the course again from the Mac: grader web-push',
  badJson: (file) => file + ' is damaged (not valid JSON). Push the course again from the Mac: grader web-push',
  missingFile: (file) => file + ' is missing. Push the course again from the Mac: grader web-push',
  noJournal: JOURNAL + ' is missing. Push the course again from the Mac: grader web-push',
  copies: (names) => 'Drive has duplicate files: ' + names.join(', ') +
    '. See the README, "Duplicate files", then reload.',
  badJournal: (lines) => JOURNAL + ' has damaged lines: ' + lines.join(', ') +
    '. See the README, "Damaged journal", then reload.',
  readError: (file) => "Couldn't read " + file + ' from Drive. Try again in a minute.',
};

// `?timing=1` shows the timing line (SPEC_discard_and_speed.md D2); the page then carries doGet's own time.
function doGet(e) {
  const t0 = Date.now();
  // Defence in depth behind "Only myself" (S2.2).
  if (Session.getActiveUser().getEmail() !== Session.getEffectiveUser().getEmail()) {
    return page_(HtmlService.createHtmlOutput(NOT_AVAILABLE_HTML));
  }
  const template = HtmlService.createTemplateFromFile('Index');
  template.timing = !!(e && e.parameter && e.parameter.timing === '1');
  const out = template.evaluate();
  const ms = Date.now() - t0;
  console.log('doGet ms=' + ms);
  return page_(out.setContent(out.getContent().replace(DOGET_SLOT, String(ms))));
}

function page_(output) {
  return output
    .setTitle(PAGE_TITLE)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// For Index.html: the content of another .html file.
function include_(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

// The pure modules, made on first use (file load order isn't guaranteed, ADR 004).
let core = null;
function core_() {
  if (!core) {
    const Csv = gwCsv();
    const Grades = gwGrades(Csv);
    core = { Csv: Csv, Grades: Grades, Journal: gwJournal(), Save: gwSave(Csv, Grades) };
  }
  return core;
}

// For Index.html: the same module source the server and the tests run, plus the instances (ADR 004).
function clientCore_() {
  return [gwCsv, gwGrades, gwJournal, gwSave].map(String).join('\n') +
    '\nconst Csv = gwCsv();\nconst Grades = gwGrades(Csv);\nconst Journal = gwJournal();\n' +
    'const Save = gwSave(Csv, Grades);\n';
}

// ---- server functions (google.script.run) ----

// {ok, now, courses}: every folder under grade_web, each available or not (S2.1, S2.3). The courses share each
// Drive listing and cache lookup, so the cost hardly grows with their number.
function listCourses() {
  return withLock_('listCourses', function () {
    const root = gradeWebFolder_();
    if (!root) return fail_('NOT_FOUND', 'No pushed courses: run `grader web-push` on the Mac');
    const folders = subfolders_(root);
    const opened = openCourses_(folders, true);
    const courses = folders.map(function (folder, i) {
      const c = opened[i].c;
      if (!c) return { folder: folder.name, available: false, reason: opened[i].reason };
      return {
        folder: folder.name, available: true, course_id: c.course.course_id, course_name: c.course.course_name,
        term: c.course.term, pushed_at: c.push.pushed_at, unpulled: c.summary.unpulled,
        last_saved: c.summary.last_saved,
        older_push: c.lines.some(function (l) { return l.push !== c.push.push_id; }),
      };
    });
    return { ok: true, courses: courses };
  });
}

// {ok, folder, course, push, roster, files, journal}: everything the browser needs to show and compute a course.
// Display only, so unchanged files may come from the cache (SPEC_discard_and_speed.md D5).
function loadCourse(folderName) {
  return withCourse_('loadCourse', folderName, function (c) {
    const rels = [c.course.roster].concat(c.course.files);
    readAll_(rels.map(function (rel) { return listedFile_(c, rel); }), c.cache);
    const files = {};
    c.course.files.forEach(function (rel) { files[rel] = readListed_(c, rel); });
    return {
      ok: true, folder: folderName, course: c.course, push: c.push, roster: readListed_(c, c.course.roster),
      files: files, journal: journalReply_(c),
    };
  }, true);
}

// Writes the unsaved edits [{student_id, column, value, original}] that still match Drive (SPEC "Saving").
// `push` = the push the edits were made on (a restored draft may predate the current one, edge 38).
function saveBatch(folderName, edits, push) {
  return withCourse_('saveBatch', folderName, function (c) {
    const plan = planFor_(c, edits, false);
    const meta = plan.changes.length ? batchMeta_(c) : null;
    if (meta) writeBatch_(c, plan, meta);
    return {
      ok: true, batch: meta && meta.batch, ts: meta && meta.ts, saved: savedCells_(plan), already: plan.already,
      conflicts: plan.conflicts, files: Object.keys(plan.texts).length,
      push_changed: !!push && push !== c.push.push_id, journal: journalReply_(c),
    };
  });
}

// Reverts the batch the teacher confirmed, if it is still the one Undo offers (SPEC "Undo last save"). Cells
// changed since come back as conflicts and keep their value (S9.2).
function undoLastSave(folderName, batch) {
  return withCourse_('undoLastSave', folderName, function (c) {
    const journal = journalReply_(c);
    if (!journal.undo) return Object.assign(fail_('UNDO_UNAVAILABLE', journal.undo_note), { journal: journal });
    if (journal.undo.batch !== batch) return Object.assign(fail_('UNDO_CHANGED', UNDO_CHANGED), { journal: journal });
    const plan = planFor_(c, core_().Save.planUndo(c.lines, batch), true);
    const meta = plan.changes.length ? Object.assign(batchMeta_(c), { undoes: batch }) : null;
    if (meta) writeBatch_(c, plan, meta);
    return {
      ok: true, batch: meta && meta.batch, undoes: batch, saved: savedCells_(plan), already: plan.already,
      conflicts: plan.conflicts, journal: journalReply_(c),
    };
  });
}

// Saves the weights or grade boundaries typed on the Grading tab (SPEC "Config save"): one `config` journal line,
// then course.json. A weights sum other than 1 comes back as `warning` and is saved (S10.2).
function saveConfig(folderName, part, value, original) {
  return withCourse_('saveConfig', folderName, function (c) {
    const plan = core_().Save.planConfig(c.course, part, value, original);
    if (plan.code === 'STALE_CONFIG') {
      return Object.assign(fail_('STALE_CONFIG', CONFIG_STALE), { current: plan.current });
    }
    if (!plan.ok) return Object.assign(fail_('INVALID', plan.field + ': not saved, the value was refused'), plan);
    const meta = batchMeta_(c);
    setPending_(c.folder, { batch: meta.batch, kind: 'config' });
    appendJournal_(c, [core_().Journal.configLine(meta, part, plan.value, c.course[part])]);
    c.course = plan.course;
    writeCourse_(c);
    clearPending_(c.folder);
    return { ok: true, batch: meta.batch, course: plan.course, warning: plan.warning, journal: journalReply_(c) };
  });
}

// ---- locking and replies ----

// Runs fn under the script lock; every reply carries the server time `now` and its `timing`.
function withLock_(name, fn) {
  const t0 = Date.now();
  resetIo_();
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(LOCK_WAIT_MS);
  } catch (e) {
    return withNow_(timed_(name, t0, Date.now(), fail_('BUSY', 'Another save is running; try again')));
  }
  const t1 = Date.now();
  try {
    return withNow_(timed_(name, t0, t1, fn()));
  } finally {
    lock.releaseLock();
  }
}

// The reply's `timing` for the ?timing=1 line, and one log line: milliseconds and Drive counts, never data.
function timed_(name, t0, t1, reply) {
  reply.timing = { ms: Date.now() - t0, lock_ms: t1 - t0, list: io.list, read: io.read, hit: io.hit, miss: io.miss };
  console.log(name + ' ms=' + reply.timing.ms + ' lock=' + reply.timing.lock_ms + ' list=' + io.list +
    ' read=' + io.read + ' hit=' + io.hit + ' miss=' + io.miss);
  return reply;
}

// Runs fn(c) under the lock on an available course (roll-forward and trim done); else NOT_FOUND / UNAVAILABLE.
// `cache` only for display calls: a call that writes or conflict-checks reads every file fresh (D5).
function withCourse_(name, folderName, fn, cache) {
  return withLock_(name, function () {
    const root = gradeWebFolder_();
    const folder = root && subfolders_(root).filter(function (f) { return f.name === folderName; })[0];
    if (!folder) return fail_('NOT_FOUND', 'No pushed course named ' + folderName);
    const opened = openCourses_([folder], !!cache)[0];
    if (!opened.c) return fail_('UNAVAILABLE', opened.reason);
    return fn(opened.c);
  });
}

function withNow_(reply) {
  reply.now = nowIso_();
  return reply;
}

function fail_(code, message) {
  return { ok: false, code: code, message: message };
}

// Server clock in the script time zone, ISO 8601 with offset: 2027-01-20T09:15:02+07:00.
function nowIso_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), ISO_FORMAT);
}

// ---- courses: trim, then the availability check ----

function Unavailable_(reason) {
  this.reason = reason;
}

// Opens course folders (grade_web listing records) for one call, in steps that each serve every folder at once:
// the folders' listing, course.json and push.json, the listed subfolders, then per course the trim and the
// availability check (SPEC "Course availability", the same order and reasons as one course at a time), the journals,
// and a pending save rolled forward. Returns per folder {c} or {reason}; c = {folder, course, push, dirs: {<rel dir>:
// [record]}, archive: [record], journalFile, journalText, lines, summary, cache}. With `cache` (display calls), files
// unchanged since they were cached are not downloaded; a course with a save pending reads fresh anyway.
function openCourses_(folders, cache) {
  const props = PropertiesService.getScriptProperties().getProperties();
  const tops = childrenOf_(folders.map(function (f) { return f.id; }));
  const its = folders.map(function (folder) {
    const tree = { '': tops[folder.id] };
    return { folder: folder, tree: tree, top: filesOf_(tree['']), reason: null,
      cache: cache && !props[pendingKey_(folder)] };
  });
  readFor_(its, function (it) { return [fileIn_(it.top, 'course.json'), fileIn_(it.top, 'push.json')]; });
  its.forEach(function (it) {
    const course = jsonOrError_(it.top, 'course.json', WHY.noCourseJson);
    it.listed = course.value ? [course.value.roster].concat(course.value.files) : [];
    it.wanted = ['archive'].concat(it.listed.map(dirOf_)).filter(function (d) { return d; });
  });
  listDirs_(its);

  its.forEach(function (it) {
    attempt_(it, function () {
      it.archive = filesOf_(it.tree.archive || []);
      trim_(it, props);
      const course = readJson_(it.top, 'course.json', WHY.noCourseJson);
      const push = readJson_(it.top, 'push.json', WHY.noPushJson);
      const listed = [course.roster].concat(course.files);
      const dirs = { '': it.top };
      listed.forEach(function (rel) {
        const dir = dirOf_(rel);
        if (!(dir in dirs)) dirs[dir] = filesOf_(it.tree[dir] || []);
      });
      const J = core_().Journal;
      let copies = [];
      Object.keys(dirs).forEach(function (dir) {
        const expected = listed.filter(function (rel) { return dirOf_(rel) === dir; }).map(baseOf_)
          .concat(dir === '' ? TOP_FILES : []);
        const found = J.conflictCopies(dirs[dir].map(function (f) { return f.name; }), expected);
        copies = copies.concat(found.map(function (n) { return dir ? dir + '/' + n : n; }));
      });
      if (copies.length) throw unavailableResetTrim_(it.folder, WHY.copies(copies));
      listed.forEach(function (rel) {
        if (!fileIn_(dirs[dirOf_(rel)], baseOf_(rel))) throw new Unavailable_(WHY.missingFile(rel));
      });
      const journalFile = fileIn_(it.top, JOURNAL);
      if (!journalFile) throw new Unavailable_(WHY.noJournal);
      it.c = { folder: it.folder, course: course, push: push, dirs: dirs, archive: it.archive, journalFile: journalFile,
        cache: it.cache };
    });
  });

  readFor_(its, function (it) { return [it.c && it.c.journalFile]; });
  return its.map(function (it) {
    attempt_(it, function () {
      const c = it.c;
      c.journalText = textOf_(c.journalFile, JOURNAL);
      const parsed = core_().Journal.parseJournal(c.journalText);
      if (parsed.bad.length) throw unavailableResetTrim_(it.folder, WHY.badJournal(parsed.bad));
      // Trimmed: every line left is unpulled (ADR 002).
      c.lines = parsed.lines;
      c.summary = core_().Journal.summary(parsed.lines);
      if (props[pendingKey_(it.folder)]) rollForward_(c, JSON.parse(props[pendingKey_(it.folder)]));
    });
    return it.reason == null ? { c: it.c } : { reason: it.reason };
  });
}

// Runs one course's step; an Unavailable_ marks the course (`reason`) and its later steps are skipped.
function attempt_(it, fn) {
  if (it.reason != null) return;
  try {
    fn();
  } catch (e) {
    if (!(e instanceof Unavailable_)) throw e;
    it.reason = e.reason;
    it.c = null;
  }
}

// Reads, for the courses still open, the files pick(it) names, in two batches: cache allowed, then fresh.
function readFor_(its, pick) {
  [true, false].forEach(function (cache) {
    let records = [];
    its.forEach(function (it) {
      if (it.reason == null && it.cache === cache) records = records.concat(pick(it).filter(Boolean));
    });
    if (records.length) readAll_(records, cache);
  });
}

// it.tree[<dir>] = the listing of each folder in it.wanted (`data`, `a/b`, `archive`), reached one level per query
// for all courses together. A folder that isn't there is left out.
function listDirs_(its) {
  for (let depth = 1; ; depth++) {
    const next = [];
    its.forEach(function (it) {
      it.wanted.forEach(function (w) {
        const segs = w.split('/');
        if (segs.length < depth) return;
        const rel = segs.slice(0, depth).join('/');
        const parent = it.tree[segs.slice(0, depth - 1).join('/')];
        if (rel in it.tree || !parent || next.some(function (n) { return n.it === it && n.rel === rel; })) return;
        const sub = parent.filter(function (r) { return r.folder && r.name === segs[depth - 1]; })[0];
        if (sub) next.push({ it: it, rel: rel, id: sub.id });
      });
    });
    if (!next.length) return;
    const kids = childrenOf_(next.map(function (n) { return n.id; }));
    next.forEach(function (n) { n.it.tree[n.rel] = kids[n.id]; });
  }
}

// Duplicate files and damaged journals are repaired by hand, and a repaired journal may hold lines that were
// already pulled. Forgetting which archives were trimmed makes the next call trim against all of them again.
function unavailableResetTrim_(folder, reason) {
  PropertiesService.getScriptProperties().deleteProperty(trimKey_(folder));
  return new Unavailable_(reason);
}

function listedFile_(c, rel) {
  return fileIn_(c.dirs[dirOf_(rel)], baseOf_(rel));
}

// The text of a listed file, downloaded unless this call has it already (fresh, or from the cache when c.cache).
function readListed_(c, rel) {
  const file = listedFile_(c, rel);
  readAll_([file], c.cache);
  return textOf_(file, rel);
}

function textOf_(file, rel) {
  if (file.error || file.text == null) throw new Unavailable_(WHY.readError(rel));
  return file.text;
}

function readJson_(files, name, missing) {
  const r = jsonOrError_(files, name, missing);
  if (r.error) throw r.error;
  return r.value;
}

// {value} or {error: Unavailable_} for a JSON file already read.
function jsonOrError_(files, name, missing) {
  const file = fileIn_(files, name);
  if (!file) return { error: new Unavailable_(missing) };
  if (file.error || file.text == null) return { error: new Unavailable_(WHY.readError(name)) };
  try {
    return { value: JSON.parse(file.text) };
  } catch (e) {
    return { error: new Unavailable_(WHY.badJson(name)) };
  }
}

function fileIn_(files, name) {
  return files.filter(function (f) { return f.name === name; })[0] || null;
}

function filesOf_(records) {
  return records.filter(function (r) { return !r.folder; });
}

function dirOf_(rel) {
  return rel.split('/').slice(0, -1).join('/');
}

function baseOf_(rel) {
  return rel.split('/').pop();
}

// The <J> part of a reply: the same two numbers web-pull prints, plus what Undo would revert.
function journalReply_(c) {
  const undo = core_().Journal.undoTarget(c.lines, c.push.push_id);
  return {
    unpulled: c.summary.unpulled, last_saved: c.summary.last_saved, undo: undo,
    undo_note: undo ? null : pulledThisPush_(c) ? NOTE_PULLED : NOTE_NONE,
  };
}

// True when the newest pull archive was written for the current push (pulls after a push carry its push_id).
function pulledThisPush_(c) {
  const pulls = c.archive.filter(function (f) {
    return /^web_edits_.*\.jsonl$/.test(f.name) && !/_discarded(-\d+)?\.jsonl$/.test(f.name);
  }).sort(function (a, b) { return a.name < b.name ? -1 : 1; });
  if (!pulls.length) return false;
  const newest = pulls[pulls.length - 1];
  readAll_([newest], c.cache);
  const header = core_().Journal.parseJournal(textOf_(newest, 'archive/' + newest.name)).lines[0];
  return !!header && header.kind === 'pull' && header.push === c.push.push_id;
}

// ---- saving (ADR 002: the journal first, then the CSVs) ----

// save.planSave over the files of the edited columns, read fresh from Drive (D5).
function planFor_(c, edits, restoring) {
  const names = edits.map(function (e) { return e.column; });
  const rels = [];
  c.course.columns.forEach(function (col) {
    if (names.indexOf(col.name) >= 0 && rels.indexOf(col.file) < 0) rels.push(col.file);
  });
  readAll_(rels.map(function (rel) { return listedFile_(c, rel); }), false);
  const files = {};
  rels.forEach(function (rel) { files[rel] = textOf_(listedFile_(c, rel), rel); });
  return core_().Save.planSave(files, c.course, edits, restoring);
}

function savedCells_(plan) {
  return plan.changes.map(function (ch) { return { student_id: ch.student_id, column: ch.column, value: ch.value }; });
}

// {batch, ts, push} of a new batch: b-YYYYMMDD-HHMMSS-xxxx on the server clock.
function batchMeta_(c) {
  const now = new Date();
  const tz = Session.getScriptTimeZone();
  const hex = ('000' + Math.floor(Math.random() * 65536).toString(16)).slice(-4);
  return {
    batch: 'b-' + Utilities.formatDate(now, tz, 'yyyyMMdd-HHmmss') + '-' + hex,
    ts: Utilities.formatDate(now, tz, ISO_FORMAT), push: c.push.push_id,
  };
}

// SPEC "Saving" step 3: the pending marker, the journal with one line per change (one write), each changed CSV
// once, then the marker cleared. A failure in between is completed or dropped by the next call (rollForward_).
function writeBatch_(c, plan, meta) {
  setPending_(c.folder, { batch: meta.batch, kind: 'cell' });
  appendJournal_(c, core_().Journal.cellLines(meta, plan.changes));
  Object.keys(plan.texts).forEach(function (rel) { writeText_(listedFile_(c, rel), plan.texts[rel]); });
  clearPending_(c.folder);
}

// The journal = its text + one line per entry, in one write; the course's lines and counts follow.
function appendJournal_(c, lines) {
  const sep = c.journalText === '' || c.journalText.slice(-1) === '\n' ? '' : '\n';
  const added = lines.map(function (l) { return JSON.stringify(l) + '\n'; }).join('');
  c.journalText = c.journalText + sep + added;
  writeText_(c.journalFile, c.journalText);
  c.lines = c.lines.concat(lines);
  c.summary = core_().Journal.summary(c.lines);
}

// course.json in web-push's layout (indent 1, Thai as is, final newline); numbers in JS form (`10`, not `10.0`).
function writeCourse_(c) {
  writeText_(fileIn_(c.dirs[''], 'course.json'), JSON.stringify(c.course, null, 1) + '\n');
}

// Completes a save that stopped after its journal append: each cell of the pending batch that still holds its
// `original` gets its `value`, and a config part that still equals its `original` gets its `value`. A batch that
// never reached the journal is just forgotten (edges 35, 36). The course was read fresh (openCourses_).
function rollForward_(c, pending) {
  const batch = c.lines.filter(function (l) { return l.batch === pending.batch; })
    .sort(function (a, b) { return a.seq - b.seq; });
  const edits = batch.filter(function (l) { return l.kind === 'cell'; })
    .map(function (l) { return { student_id: l.student_id, column: l.column, value: l.value, original: l.original }; });
  if (edits.length) {
    const plan = planFor_(c, edits, true);
    Object.keys(plan.texts).forEach(function (rel) { writeText_(listedFile_(c, rel), plan.texts[rel]); });
  }
  batch.forEach(function (l) {
    if (l.kind !== 'config' || !core_().Save.sameConfig(c.course[l.part], l.original)) return;
    const part = {};
    part[l.part] = l.value;
    c.course = Object.assign({}, c.course, part);
    writeCourse_(c);
  });
  clearPending_(c.folder);
}

// ---- trim (ADR 002) ----

function trimKey_(folder) {
  return 'trimmed:' + folder.id;
}

// Removes from the journal the lines whose key is in an archive file not trimmed against yet, then records those
// archive names (a cache: trimming again changes nothing). Skipped while the journal is missing or duplicated.
// Reads fresh; a read failure throws Unavailable_. `props`: the ScriptProperties read at the start of the call.
function trim_(it, props) {
  const done = JSON.parse(props[trimKey_(it.folder)] || '[]');
  const fresh = it.archive.filter(function (f) { return /\.jsonl$/.test(f.name) && done.indexOf(f.name) < 0; });
  if (!fresh.length) return;
  const journals = it.top.filter(function (f) { return f.name === JOURNAL; });
  if (journals.length !== 1) return;
  const J = core_().Journal;
  readAll_(fresh.concat(journals), false);
  const texts = fresh.map(function (f) { return textOf_(f, 'archive/' + f.name); });
  const keys = new Set(J.archivedKeys(texts));
  const text = textOf_(journals[0], JOURNAL);
  const trimmed = J.trim(text, keys);
  if (trimmed !== text) writeText_(journals[0], trimmed);
  const names = done.concat(fresh.map(function (f) { return f.name; }));
  PropertiesService.getScriptProperties().setProperty(trimKey_(it.folder), JSON.stringify(names));
  props[trimKey_(it.folder)] = JSON.stringify(names);
}

// T1 spike, run once from the editor (Run menu). Writes a fake Thai + BOM + CRLF CSV under
// grade_web/_spike/ the way drive.js will (createFile, then setContent), reads it back and compares
// byte for byte, then trashes the file and the folder. Public (no trailing _) because the editor's
// Run menu hides private functions.
function spikeRoundTrip() {
  const created = '﻿' + [
    'Student ID,Name,hw1,midterm,total',
    '9900000001,นายสมมติ ทดสอบ,8.5,20,28.5',
    '9900000002,"นางสาวจำลอง, ใจดี",ขส,,0',
    '9900000003,"เด็กชาย ""น้ำ"" ตัวอย่าง",10,15,25',
    '',
  ].join('\r\n');
  const spliced = created.replace(',8.5,', ',9,');

  const found = gradeWebFolder_();
  const root = found ? DriveApp.getFolderById(found.id) : DriveApp.getRootFolder().createFolder(GRADE_WEB);
  const folder = root.createFolder('_spike');
  let file = null;
  let pass = false;
  try {
    file = folder.createFile('roundtrip.csv', created, MimeType.CSV);
    const a = spikeCheck_('createFile bytes', utf8Bytes_(created), driveBytes_(file));
    file.setContent(spliced);
    const b = spikeCheck_('setContent bytes', utf8Bytes_(spliced), driveBytes_(file));
    const text = file.getBlob().getDataAsString();
    const c = spikeCheck_('getDataAsString text', utf8Bytes_(spliced), utf8Bytes_(text));
    pass = a && b && c;
  } finally {
    if (file) file.setTrashed(true);
    folder.setTrashed(true);
  }
  console.log(pass ? 'SPIKE PASS' : 'SPIKE FAIL');
  return pass;
}

function spikeCheck_(label, expected, actual) {
  const at = firstDiff_(expected, actual);
  console.log((at < 0 ? 'PASS ' : 'FAIL ') + label + ': expected ' + expected.length +
    ' bytes, got ' + actual.length + (at < 0 ? '' : ', first difference at byte ' + at));
  return at < 0;
}

// Fresh read from Drive, as unsigned bytes (Apps Script bytes are signed).
function driveBytes_(file) {
  return DriveApp.getFileById(file.getId()).getBlob().getBytes().map(function (b) { return b & 0xff; });
}

function utf8Bytes_(text) {
  const bin = unescape(encodeURIComponent(text));
  const bytes = [];
  for (let i = 0; i < bin.length; i++) bytes.push(bin.charCodeAt(i));
  return bytes;
}

// Index of the first differing byte, or -1 when equal.
function firstDiff_(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return i;
  return a.length === b.length ? -1 : n;
}
