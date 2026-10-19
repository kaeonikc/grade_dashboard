// drive.js: DriveApp I/O only (web/SPEC.md "Modules"). Folders and files are found by name, never by a stored ID.
// DriveApp iterators can include trashed items, so every listing skips them.

const GRADE_WEB = 'grade_web';

function untrashed_(it) {
  const items = [];
  while (it.hasNext()) {
    const item = it.next();
    if (!item.isTrashed()) items.push(item);
  }
  return items;
}

// My Drive/grade_web, or null when it doesn't exist.
function gradeWebFolder_() {
  return untrashed_(DriveApp.getRootFolder().getFoldersByName(GRADE_WEB))[0] || null;
}

function subfolder_(folder, name) {
  return untrashed_(folder.getFoldersByName(name))[0] || null;
}

// The folder at a relative path like `data` or `a/b` (`` = the folder itself), or null.
function folderAt_(folder, rel) {
  let f = folder;
  for (const name of rel.split('/').filter(Boolean)) {
    f = subfolder_(f, name);
    if (!f) return null;
  }
  return f;
}

function subfolders_(folder) {
  return untrashed_(folder.getFolders()).sort((a, b) => (a.getName() < b.getName() ? -1 : 1));
}

// Files directly in the folder, duplicate names included.
function filesIn_(folder) {
  return untrashed_(folder.getFiles());
}

// UTF-8 text; a BOM stays as U+FEFF.
function readText_(file) {
  return file.getBlob().getDataAsString();
}

function writeText_(file, text) {
  file.setContent(text);
}

// The marker of a save in progress (SPEC "Saving" step 3), kept in ScriptProperties under the folder's id.
function pendingKey_(folder) {
  return 'pending:' + folder.getId();
}

function getPending_(folder) {
  const value = PropertiesService.getScriptProperties().getProperty(pendingKey_(folder));
  return value ? JSON.parse(value) : null;
}

function setPending_(folder, marker) {
  PropertiesService.getScriptProperties().setProperty(pendingKey_(folder), JSON.stringify(marker));
}

function clearPending_(folder) {
  PropertiesService.getScriptProperties().deleteProperty(pendingKey_(folder));
}
