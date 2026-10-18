// grade_web server (Apps Script V8). Executes as the owner, access "Only myself".
// Logs hold only codes, byte counts and offsets: no names, IDs or scores.

const PAGE_TITLE = 'grade_web';
const GRADE_WEB = 'grade_web';

const NOT_AVAILABLE_HTML =
  '<h1>Not available</h1><p>This page opens only for the Google account that owns it.</p>';

function doGet() {
  // Defence in depth behind "Only myself" (S2.2).
  if (Session.getActiveUser().getEmail() !== Session.getEffectiveUser().getEmail()) {
    return page_(HtmlService.createHtmlOutput(NOT_AVAILABLE_HTML));
  }
  const template = HtmlService.createTemplateFromFile('Index');
  const root = gradeWebFolder_();
  template.folders = root ? folderNames_(root) : null;
  return page_(template.evaluate());
}

function page_(output) {
  return output
    .setTitle(PAGE_TITLE)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// My Drive/grade_web, or null when it doesn't exist. DriveApp iterators include trashed items.
function gradeWebFolder_() {
  const it = DriveApp.getRootFolder().getFoldersByName(GRADE_WEB);
  while (it.hasNext()) {
    const folder = it.next();
    if (!folder.isTrashed()) return folder;
  }
  return null;
}

function folderNames_(folder) {
  const names = [];
  const it = folder.getFolders();
  while (it.hasNext()) {
    const child = it.next();
    if (!child.isTrashed()) names.push(child.getName());
  }
  return names.sort();
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
