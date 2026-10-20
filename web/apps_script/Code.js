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

// {ok, now, courses}: every folder under grade_web, each available or not (S2.1, S2.3).
function listCourses() {
  return withLock_('listCourses', function () {
    const root = gradeWebFolder_();
    if (!root) return fail_('NOT_FOUND', 'No pushed courses: run `grader web-push` on the Mac');
    const courses = subfolders_(root).map(function (folder) {
      const name = folder.getName();
      try {
        const c = openCourse_(folder);
        return {
          folder: name, available: true, course_id: c.course.course_id, course_name: c.course.course_name,
          term: c.course.term, pushed_at: c.push.pushed_at, unpulled: c.summary.unpulled,
          last_saved: c.summary.last_saved,
          older_push: c.lines.some(function (l) { return l.push !== c.push.push_id; }),
        };
      } catch (e) {
        if (!(e instanceof Unavailable_)) throw e;
        return { folder: name, available: false, reason: e.reason };
      }
    });
    return { ok: true, courses: courses };
  });
}

// {ok, folder, course, push, roster, files, journal}: everything the browser needs to show and compute a course.
function loadCourse(folderName) {
  return withCourse_('loadCourse', folderName, function (c) {
    const files = {};
    c.course.files.forEach(function (rel) { files[rel] = readListed_(c, rel); });
    return {
      ok: true, folder: folderName, course: c.course, push: c.push, roster: readListed_(c, c.course.roster),
      files: files, journal: journalReply_(c),
    };
  });
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
function withCourse_(name, folderName, fn) {
  return withLock_(name, function () {
    const root = gradeWebFolder_();
    const folder = root && subfolder_(root, folderName);
    if (!folder) return fail_('NOT_FOUND', 'No pushed course named ' + folderName);
    let c;
    try {
      c = openCourse_(folder);
    } catch (e) {
      if (!(e instanceof Unavailable_)) throw e;
      return fail_('UNAVAILABLE', e.reason);
    }
    return fn(c);
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

// ---- one course: trim, then the availability check ----

function Unavailable_(reason) {
  this.reason = reason;
}

// Trims the journal, checks the course can be used (SPEC "Course availability"), then rolls a pending save
// forward. Throws Unavailable_. Returns {folder, course, push, dirs: {<rel dir>: [File]}, journalFile,
// journalText, lines, summary}. The data files are only found here; readListed_ reads them.
function openCourse_(folder) {
  trim_(folder);
  const top = filesIn_(folder);
  const course = readJson_(top, 'course.json', WHY.noCourseJson);
  const push = readJson_(top, 'push.json', WHY.noPushJson);
  const listed = [course.roster].concat(course.files);
  const dirs = { '': top };
  listed.forEach(function (rel) {
    const dir = dirOf_(rel);
    if (!(dir in dirs)) {
      const sub = folderAt_(folder, dir);
      dirs[dir] = sub ? filesIn_(sub) : [];
    }
  });

  const J = core_().Journal;
  let copies = [];
  Object.keys(dirs).forEach(function (dir) {
    const expected = listed.filter(function (rel) { return dirOf_(rel) === dir; }).map(baseOf_)
      .concat(dir === '' ? TOP_FILES : []);
    const found = J.conflictCopies(dirs[dir].map(function (f) { return f.getName(); }), expected);
    copies = copies.concat(found.map(function (n) { return dir ? dir + '/' + n : n; }));
  });
  if (copies.length) throw unavailableResetTrim_(folder, WHY.copies(copies));

  listed.forEach(function (rel) {
    if (!fileIn_(dirs[dirOf_(rel)], baseOf_(rel))) throw new Unavailable_(WHY.missingFile(rel));
  });

  const journalFile = fileIn_(top, JOURNAL);
  if (!journalFile) throw new Unavailable_(WHY.noJournal);
  const journalText = readOrUnavailable_(journalFile, JOURNAL);
  const parsed = J.parseJournal(journalText);
  if (parsed.bad.length) throw unavailableResetTrim_(folder, WHY.badJournal(parsed.bad));
  // Trimmed: every line left is unpulled (ADR 002).
  const c = {
    folder: folder, course: course, push: push, dirs: dirs, journalFile: journalFile, journalText: journalText,
    lines: parsed.lines, summary: J.summary(parsed.lines),
  };
  rollForward_(c);
  return c;
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

function readListed_(c, rel) {
  return readOrUnavailable_(listedFile_(c, rel), rel);
}

function readJson_(files, name, missing) {
  const file = fileIn_(files, name);
  if (!file) throw new Unavailable_(missing);
  try {
    return JSON.parse(readOrUnavailable_(file, name));
  } catch (e) {
    if (e instanceof Unavailable_) throw e;
    throw new Unavailable_(WHY.badJson(name));
  }
}

function readOrUnavailable_(file, rel) {
  try {
    return readText_(file);
  } catch (e) {
    throw new Unavailable_(WHY.readError(rel));
  }
}

function fileIn_(files, name) {
  return files.filter(function (f) { return f.getName() === name; })[0] || null;
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
  const archive = subfolder_(c.folder, 'archive');
  const pulls = (archive ? filesIn_(archive) : []).filter(function (f) {
    return /^web_edits_.*\.jsonl$/.test(f.getName()) && !/_discarded(-\d+)?\.jsonl$/.test(f.getName());
  }).sort(function (a, b) { return a.getName() < b.getName() ? -1 : 1; });
  if (!pulls.length) return false;
  const newest = pulls[pulls.length - 1];
  const header = core_().Journal.parseJournal(readOrUnavailable_(newest, 'archive/' + newest.getName())).lines[0];
  return !!header && header.kind === 'pull' && header.push === c.push.push_id;
}

// ---- saving (ADR 002: the journal first, then the CSVs) ----

// save.planSave over the files of the edited columns.
function planFor_(c, edits, restoring) {
  const names = edits.map(function (e) { return e.column; });
  const files = {};
  c.course.columns.forEach(function (col) {
    if (names.indexOf(col.name) >= 0 && !(col.file in files)) files[col.file] = readListed_(c, col.file);
  });
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
// never reached the journal is just forgotten (edges 35, 36).
function rollForward_(c) {
  const pending = getPending_(c.folder);
  if (!pending) return;
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
  return 'trimmed:' + folder.getId();
}

// Removes from the journal the lines whose key is in an archive file not trimmed against yet, then records those
// archive names (a cache: trimming again changes nothing). Skipped while the journal is missing or duplicated.
// A read failure throws Unavailable_.
function trim_(folder) {
  const archive = subfolder_(folder, 'archive');
  if (!archive) return;
  const props = PropertiesService.getScriptProperties();
  const done = JSON.parse(props.getProperty(trimKey_(folder)) || '[]');
  const fresh = filesIn_(archive).filter(function (f) {
    return /\.jsonl$/.test(f.getName()) && done.indexOf(f.getName()) < 0;
  });
  if (!fresh.length) return;
  const journals = filesIn_(folder).filter(function (f) { return f.getName() === JOURNAL; });
  if (journals.length !== 1) return;
  const J = core_().Journal;
  const texts = fresh.map(function (f) { return readOrUnavailable_(f, 'archive/' + f.getName()); });
  const keys = new Set(J.archivedKeys(texts));
  const text = readOrUnavailable_(journals[0], JOURNAL);
  const trimmed = J.trim(text, keys);
  if (trimmed !== text) writeText_(journals[0], trimmed);
  props.setProperty(trimKey_(folder), JSON.stringify(done.concat(fresh.map(function (f) { return f.getName(); }))));
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

  const root = gradeWebFolder_() || DriveApp.getRootFolder().createFolder(GRADE_WEB);
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
