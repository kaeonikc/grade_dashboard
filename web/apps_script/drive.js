// drive.js: Drive I/O only (web/SPEC.md "Modules"). Folders and files are found by name in each call's own listing,
// never by a stored ID. Listings go through the Advanced Drive service (v3): one query covers many folders and leaves
// trashed items out. Reads and writes stay on DriveApp (byte-exact, T1 spike). File text is cached in CacheService
// under the file's id and md5, so a changed file never hits an old entry (SPEC_discard_and_speed.md D3-D5).

const GRADE_WEB = 'grade_web';
const FOLDER_MIME = 'application/vnd.google-apps.folder';
const LIST_FIELDS = 'nextPageToken, files(id, name, mimeType, md5Checksum, parents)';
const PARENTS_PER_LIST = 40;
const CACHE_PREFIX = 'gw1:';
const CACHE_TTL_S = 21600;  // 6 h, CacheService's longest
const CHUNK = 30000;        // UTF-16 units per cached value: at most 90 000 UTF-8 bytes (the limit is 100 KB)

// Drive work of the current server call, for the ?timing=1 line and the log (withLock_ resets it): listings,
// downloads, and content-cache hits and misses. Counts only, never names.
let io = { list: 0, read: 0, hit: 0, miss: 0 };

function resetIo_() {
  io = { list: 0, read: 0, hit: 0, miss: 0 };
}

// A listed Drive item: {id, name, folder, md5}. readAll_ and writeText_ add `text` (and `fresh` when that text came
// from Drive in this call rather than from the cache), or `error` when the download failed.
function record_(f) {
  return { id: f.id, name: f.name, folder: f.mimeType === FOLDER_MIME, md5: f.md5Checksum || null };
}

// [{rec, parents}] of one query, every page.
function listQuery_(q) {
  const out = [];
  let token = null;
  do {
    io.list++;
    const params = { q: q, fields: LIST_FIELDS, pageSize: 1000 };
    if (token) params.pageToken = token;
    const reply = Drive.Files.list(params);
    (reply.files || []).forEach(function (f) { out.push({ rec: record_(f), parents: f.parents || [] }); });
    token = reply.nextPageToken;
  } while (token);
  return out;
}

// {<folder id>: [record]}: each folder's untrashed children, duplicate names kept, PARENTS_PER_LIST folders a query.
function childrenOf_(ids) {
  const out = {};
  ids.forEach(function (id) { out[id] = []; });
  for (let i = 0; i < ids.length; i += PARENTS_PER_LIST) {
    const part = ids.slice(i, i + PARENTS_PER_LIST);
    const q = '(' + part.map(function (id) { return "'" + id + "' in parents"; }).join(' or ') + ') and trashed = false';
    listQuery_(q).forEach(function (item) {
      item.parents.forEach(function (p) { if (p in out) out[p].push(item.rec); });
    });
  }
  return out;
}

// My Drive/grade_web, or null when it doesn't exist.
function gradeWebFolder_() {
  const q = "'root' in parents and name = '" + GRADE_WEB + "' and mimeType = '" + FOLDER_MIME + "' and trashed = false";
  return listQuery_(q).map(function (item) { return item.rec; })[0] || null;
}

// The folders directly in a folder, by name.
function subfolders_(folder) {
  return childrenOf_([folder.id])[folder.id].filter(function (r) { return r.folder; })
    .sort(function (a, b) { return a.name < b.name ? -1 : 1; });
}

// Fills in each record's text. With `cache`, unchanged files come from CacheService (one lookup for all) and only the
// rest are downloaded; without it, each file not yet read from Drive in this call is downloaded. A failed download
// sets `error`. Downloads go into the cache either way.
function readAll_(records, cache) {
  const todo = records.filter(function (r) { return r.text == null || !(cache || r.fresh); });
  let left = todo;
  if (cache) {
    const found = cacheGet_(todo.filter(function (r) { return r.md5; }));
    left = todo.filter(function (r) {
      if (!(r.id in found)) return true;
      r.text = found[r.id];
      r.fresh = false;
      io.hit++;
      return false;
    });
    io.miss += left.length;
  }
  const fetched = [];
  left.forEach(function (r) {
    try {
      r.text = readText_(r);
      r.fresh = true;
      delete r.error;
      fetched.push(r);
    } catch (e) {
      r.error = e;
    }
  });
  cachePut_(fetched);
}

// UTF-8 text; a BOM stays as U+FEFF.
function readText_(record) {
  io.read++;
  return DriveApp.getFileById(record.id).getBlob().getDataAsString();
}

// Writes the file, then keeps the text for the rest of the call and in the cache, under the md5 of the bytes written.
function writeText_(record, text) {
  DriveApp.getFileById(record.id).setContent(text);
  record.text = text;
  record.fresh = true;
  record.md5 = md5Hex_(text);
  cachePut_([record]);
}

function md5Hex_(text) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, text, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}

// ---- the content cache: `T<text>` under the key, or `C<n>` there and the text in n chunks under `<key>:<i>` ----

function cacheKey_(record) {
  return CACHE_PREFIX + record.id + ':' + record.md5;
}

// {<id>: text} of the records found whole in the cache. A missing chunk or a cache failure reads as not found.
function cacheGet_(records) {
  if (!records.length) return {};
  try {
    const cache = CacheService.getScriptCache();
    const heads = cache.getAll(records.map(cacheKey_));
    const out = {};
    const chunked = [];
    records.forEach(function (r) {
      const v = heads[cacheKey_(r)];
      if (v == null) return;
      if (v.charAt(0) === 'T') out[r.id] = v.slice(1);
      else if (v.charAt(0) === 'C') chunked.push({ r: r, n: +v.slice(1) });
    });
    if (chunked.length) {
      const keys = [];
      chunked.forEach(function (c) { for (let i = 0; i < c.n; i++) keys.push(cacheKey_(c.r) + ':' + i); });
      const parts = cache.getAll(keys);
      chunked.forEach(function (c) {
        const texts = [];
        for (let i = 0; i < c.n; i++) {
          const part = parts[cacheKey_(c.r) + ':' + i];
          if (part == null) return;
          texts.push(part);
        }
        out[c.r.id] = texts.join('');
      });
    }
    return out;
  } catch (e) {
    console.log('cache_error get');
    return {};
  }
}

function cachePut_(records) {
  const values = {};
  records.forEach(function (r) {
    if (!r.md5) return;
    const key = cacheKey_(r);
    if (r.text.length <= CHUNK) {
      values[key] = 'T' + r.text;
      return;
    }
    const parts = chunks_(r.text);
    values[key] = 'C' + parts.length;
    parts.forEach(function (part, i) { values[key + ':' + i] = part; });
  });
  if (!Object.keys(values).length) return;
  try {
    CacheService.getScriptCache().putAll(values, CACHE_TTL_S);
  } catch (e) {
    console.log('cache_error put');
  }
}

// The text in pieces of at most CHUNK units, never splitting a surrogate pair.
function chunks_(text) {
  const out = [];
  let i = 0;
  while (i < text.length) {
    let j = Math.min(i + CHUNK, text.length);
    const c = text.charCodeAt(j - 1);
    if (j < text.length && c >= 0xd800 && c <= 0xdbff) j--;
    out.push(text.slice(i, j));
    i = j;
  }
  return out;
}

// ---- ScriptProperties markers, under the course folder's id ----

// The marker of a save in progress (SPEC "Saving" step 3).
function pendingKey_(folder) {
  return 'pending:' + folder.id;
}

function setPending_(folder, marker) {
  PropertiesService.getScriptProperties().setProperty(pendingKey_(folder), JSON.stringify(marker));
}

function clearPending_(folder) {
  PropertiesService.getScriptProperties().deleteProperty(pendingKey_(folder));
}
