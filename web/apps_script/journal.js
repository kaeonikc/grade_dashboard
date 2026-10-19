// journal.js: the edit journal web_edits.jsonl and the messages built from it (web/SPEC.md "Journal",
// "User-facing messages"). One factory, no globals (ADR 004). Injected into the browser too, for `fmt`.
function gwJournal() {
  'use strict';

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const COPY = /^(.*) \(\d+\)(\.[^.]*)?$/;  // Drive's conflict copy of `<stem><ext>`: `<stem> (1)<ext>`
  const UNDO_LIST = 10;

  const key = (line) => line.batch + '#' + line.seq;

  // One journal line, or null when the text isn't a JSON object.
  function lineOf(text) {
    let obj;
    try {
      obj = JSON.parse(text);
    } catch (e) {
      return null;
    }
    return obj !== null && typeof obj === 'object' && !Array.isArray(obj) ? obj : null;
  }

  // {lines, bad}: the valid lines in order and the 1-based numbers of the others. Blank lines are neither.
  function parseJournal(text) {
    const lines = [];
    const bad = [];
    text.split('\n').forEach((t, i) => {
      if (t.trim() === '') return;
      const line = lineOf(t);
      if (line) lines.push(line); else bad.push(i + 1);
    });
    return { lines, bad };
  }

  // `batch#seq` of every line in the archive texts (a header line has no key).
  function archivedKeys(texts) {
    const keys = [];
    for (const t of texts) {
      for (const line of parseJournal(t).lines) if ('batch' in line && 'seq' in line) keys.push(key(line));
    }
    return keys;
  }

  function unpulled(lines, keys) {
    return lines.filter((l) => !keys.has(key(l)));
  }

  function summary(lines) {
    let last = null;
    for (const l of lines) if (last === null || String(l.ts) > last) last = String(l.ts);
    return { unpulled: lines.length, last_saved: last };
  }

  // The journal text without the lines whose key is archived. Every other line (invalid ones included) keeps its
  // bytes and place (ADR 002).
  function trim(text, keys) {
    return text.split('\n').filter((t) => {
      const line = t.trim() === '' ? null : lineOf(t);
      return !(line && keys.has(key(line)));
    }).join('\n');
  }

  // Names in one folder that Drive made when two writers met: a second file with the same name, or
  // `<stem> (<n>)<ext>` whose `<stem><ext>` is an expected file (edge 17). Each reported once, in listing order.
  function conflictCopies(names, expected) {
    const seen = new Set();
    const out = [];
    for (const n of names) {
      const m = COPY.exec(n);
      const copy = m !== null && expected.indexOf(m[1] + (m[2] || '')) >= 0;
      if ((seen.has(n) || copy) && out.indexOf(n) < 0) out.push(n);
      seen.add(n);
    }
    return out;
  }

  // The save Undo offers: among unpulled lines of the current push, the newest cell batch that neither undoes nor
  // has been undone (S9.5). {batch, ts, cells, edits: the first 10 cells in seq order} or null.
  function undoTarget(lines, pushId) {
    const undone = new Set(lines.filter((l) => l.undoes).map((l) => l.undoes));
    let batch = null;
    for (const l of lines) {
      const offered = l.kind === 'cell' && l.push === pushId && !l.undoes && !undone.has(l.batch);
      if (offered && (batch === null || l.batch > batch)) batch = l.batch;
    }
    if (batch === null) return null;
    const cells = lines.filter((l) => l.batch === batch && l.kind === 'cell').sort((a, b) => a.seq - b.seq);
    return {
      batch, ts: cells[0].ts, cells: cells.length,
      edits: cells.slice(0, UNDO_LIST).map((l) => ({
        student_id: l.student_id, column: l.column, value: l.value, original: l.original,
      })),
    };
  }

  // The journal lines of one batch, fields in the order of SPEC's journal example. meta = {batch, ts, push} plus
  // `undoes` for an undo batch; changes = [{student_id, column, file, value, original}].
  function cellLines(meta, changes) {
    return changes.map((c, seq) => {
      const line = {
        batch: meta.batch, seq, ts: meta.ts, kind: 'cell', push: meta.push, file: c.file,
        student_id: String(c.student_id), column: c.column, value: c.value, original: c.original,
      };
      if (meta.undoes) line.undoes = meta.undoes;
      return line;
    });
  }

  function configLine(meta, part, value, original) {
    return { batch: meta.batch, seq: 0, ts: meta.ts, kind: 'config', push: meta.push, part, value, original };
  }

  // ---- message formatters (Interface "Formats" and the copy table) ----
  function plural(n, word) {
    return n + ' ' + word + (n === 1 ? '' : 's');
  }

  // Date and time as written in the ISO text (its own offset, the server clock), never the device's zone.
  function parts(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
    return { y: +m[1], mon: MONTHS[+m[2] - 1], d: +m[3], hm: m[4] + ':' + m[5] };
  }

  // `20 Jan 09:15` in the current year, `30 Dec 2026 21:05` otherwise.
  function fmtTime(iso, nowIso) {
    const t = parts(iso);
    const year = t.y === parts(nowIso).y ? '' : ' ' + t.y;
    return t.d + ' ' + t.mon + year + ' ' + t.hm;
  }

  function fmtAgo(iso, nowIso) {
    const min = Math.floor((Date.parse(nowIso) - Date.parse(iso)) / 60000);
    if (min < 1) return 'just now';
    if (min < 60) return min + ' min ago';
    if (min < 24 * 60) return Math.floor(min / 60) + ' h ago';
    return plural(Math.floor(min / (24 * 60)), 'day') + ' ago';
  }

  function draftAge(madeAt, nowIso) {
    const old = Date.parse(nowIso) - Date.parse(madeAt) >= 24 * 3600 * 1000;
    return 'from ' + fmtTime(madeAt, nowIso) + (old ? ', ' + fmtAgo(madeAt, nowIso) : '');
  }

  // `4 edits not pulled · last saved 20 Jan 09:15` (the same two numbers grader web-pull prints, edge 15).
  function journalLine(s, nowIso) {
    if (!s.unpulled) return 'No edits waiting to be pulled';
    return plural(s.unpulled, 'edit') + ' not pulled · last saved ' + fmtTime(s.last_saved, nowIso);
  }

  const LISTED = 3;  // cells named in a result message before "and {k} more"
  const shown = (value) => (String(value).trim() === '' ? 'blank' : value);

  // `9900000001 hw2 (now 7), …` for the first 3, then ` and {k} more`.
  function cellList(cells, withNow) {
    const names = cells.slice(0, LISTED).map((c) => c.student_id + ' ' + c.column +
      (withNow && c.now != null ? ' (now ' + shown(c.now) + ')' : ''));
    return names.join(', ') + (cells.length > LISTED ? ' and ' + (cells.length - LISTED) + ' more' : '');
  }

  // The Save result (copy table save.ok, save.conflicts, save.notFound, save.pushChanged). Saved counts saved +
  // already, so a Retry after a lost reply reads like the original save; "(N files)" = the distinct
  // columns[].file of those cells.
  function saveResult(reply, columns) {
    const done = reply.saved.concat(reply.already);
    const fileOf = new Map(columns.map((c) => [c.name, c.file]));
    const files = new Set(done.map((c) => fileOf.get(c.column)));
    const of = (reason) => reply.conflicts.filter((c) => c.reason === reason);
    const changed = of('changed');
    const notFound = of('not found');
    const invalid = of('invalid');
    let text = 'Saved ' + plural(done.length, 'cell');
    if (!reply.conflicts.length) text += ' (' + plural(files.size, 'file') + ')';
    if (changed.length) text += ' · ' + changed.length + ' changed elsewhere, not saved: ' + cellList(changed, true);
    if (notFound.length) {
      text += ' · ' + notFound.length + ' not found (student or column not in this course): ' + cellList(notFound);
    }
    if (invalid.length) text += ' · ' + invalid.length + ' refused by Drive (not a valid score): ' + cellList(invalid);
    if (reply.push_changed) {
      text += '. Some edits were made before the latest push; they were checked against the new data.';
    }
    return text;
  }

  function undoTitle(target, nowIso) {
    return 'Undo save of ' + fmtTime(target.ts, nowIso) + ', ' + plural(target.cells, 'cell') + '?';
  }

  // The undoLastSave result (copy table undo.ok, undo.partial, undo.noneDone).
  function undoResult(reply, target, nowIso) {
    const n = reply.saved.length + reply.already.length;
    const c = reply.conflicts.length;
    if (!c) return 'Undid save of ' + fmtTime(target.ts, nowIso) + ': ' + plural(n, 'cell') + ' restored';
    const left = c + ' changed since, left as is: ' + cellList(reply.conflicts, true);
    if (!n) return 'Nothing undone · ' + left;
    return 'Undid ' + n + ' of ' + plural(target.cells, 'cell') + ' · ' + left;
  }

  return {
    key, parseJournal, archivedKeys, unpulled, summary, trim, conflictCopies, undoTarget, cellLines, configLine,
    fmt: { plural, fmtTime, fmtAgo, draftAge, journalLine, saveResult, undoTitle, undoResult },
  };
}
if (typeof module !== 'undefined') module.exports = gwJournal;
