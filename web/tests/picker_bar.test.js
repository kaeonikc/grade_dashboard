'use strict';
// The marked cell and a phone's P/L/A/X grid (SPEC_picker_bar.md). client_views.html needs a browser, so here its shape
// is checked from the source and the colours are computed; browser/picker_bar.js drives the real page.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const H = require('./helpers.js');

const VIEWS = fs.readFileSync(path.join(H.APPS, 'client_views.html'), 'utf8');
const css = H.readText(path.join(H.APPS, 'style.html'));

// The body of a top-level `function name(`.
const fn = (name) => {
  const start = VIEWS.indexOf('function ' + name + '(');
  assert.ok(start >= 0, name);
  return VIEWS.slice(start, VIEWS.indexOf('\n}\n', start));
};

test('D1: the cell, its name and its head get a mark that a class carries', () => {
  assert.match(fn('markCell'), /classList\.add\('picked'\)/);
  assert.match(fn('markCell'), /tb\.headRow\.children\[c\]/);
  assert.match(fn('markCell'), /kind === 'name'/);
  assert.doesNotMatch(fn('markCell'), /aria-pressed/);
  assert.match(fn('clearMark'), /classList\.remove\('picked', 'pick-line'\)/);
});

test('D1: the mark is solid and beats a stripe', () => {
  const rule = css.match(/\.tb td\.picked, \.tb td\.pick-line, \.tb thead th\.pick-line, \.tb tr\.stripe td\.picked, \.tb tr\.stripe td\.pick-line \{([^}]+)\}/);
  assert.ok(rule);
  assert.match(rule[1], /background-color: color-mix\(in srgb, var\(--accent\) 18%, var\(--bg\)\)/);
  assert.match(rule[1], /background-image: none/);
  assert.ok(rule.index > css.indexOf('.tb tr.stripe td.unsaved'), 'after the stripes and the unsaved amber');
});

test('D2: a phone floats a grid beside the cell, a computer the pop-up under it', () => {
  const open = fn('openPicker');
  assert.match(open, /cm\.wrap\.append\(box\);\n\s+if \(phone\) \{\n\s+box\.classList\.add\('picker-grid'\);\n\s+placeGrid\(box, rec\.tds\[c\]\);/);
  assert.match(open, /\} else \{\n\s+place\(box, rec\.tds\[c\]\);/);
  assert.match(open, /focus\(\{ preventScroll: phone \}\)/);
});

test('D2: nothing moves the rows on a phone', () => {
  assert.doesNotMatch(fn('openPicker'), /revealCell|scrollBy|scrollTo\(|scrollIntoView/);
  assert.doesNotMatch(fn('placeGrid'), /scrollBy|scrollTo\(|scrollIntoView/);
  assert.match(fn('focusCell'), /td\.focus\(\{ preventScroll: still \}\)/);
  assert.match(fn('tableClick'), /focusCell\(r, c, !WIDE\.matches\)/);
  assert.match(fn('openPicker'), /keySet\(r, c, code, false\);\n\s+focusCell\(r, c, !WIDE\.matches\);/);
});

test('D2: the grid is small, with 36 px buttons', () => {
  assert.match(css, /\.tb-picker\.picker-grid \{ display: grid; grid-template-columns: repeat\(2, 2\.25rem\);/);
  const btn = css.match(/\.picker-grid \.btn \{([^}]+)\}/)[1];
  assert.match(btn, /min-height: 2\.25rem/);
  assert.match(btn, /min-width: 0/);
});

// pickerSpot from client_state.html, on its own: it reads nothing but its arguments.
const STATE = fs.readFileSync(path.join(H.APPS, 'client_state.html'), 'utf8');
const pickerSpot = new Function('return ' + STATE.slice(STATE.indexOf('function pickerSpot('), STATE.indexOf('</script>', STATE.indexOf('function pickerSpot('))))();
const SIZE = { width: 80, height: 108 };
const CELL = { width: 56, height: 40 };
const clash = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

// Every place a cell can show at a screen size, a pixel step apart.
function everyCell(w, wrap, rows) {
  for (let top = rows.top - CELL.height + 1; top < rows.bottom; top += 3) {
    for (let left = rows.left - CELL.width + 1; left < rows.right; left += 3) {
      const cell = { left, top, right: left + CELL.width, bottom: top + CELL.height };
      const at = pickerSpot(cell, SIZE, rows, wrap);
      const box = { left: at.x, top: at.y, right: at.x + SIZE.width, bottom: at.y + SIZE.height };
      const where = JSON.stringify({ cell, box });
      assert.ok(!clash(box, cell), 'over the cell: ' + where);
      assert.ok(box.left >= rows.left, 'over the names: ' + where);
      assert.ok(box.right <= w, 'off the right: ' + where);
      assert.ok(box.top >= wrap.top && box.bottom <= wrap.bottom, 'off the grid: ' + where);
    }
  }
}

test('D2: at every cell position the grid is on screen, off the cell and off the names', () => {
  everyCell(375, { top: 188, bottom: 599 }, { left: 152, right: 375, top: 238, bottom: 559 });  // 375×665
  everyCell(320, { top: 188.5, bottom: 502 }, { left: 152, right: 320, top: 239.5, bottom: 462 });  // 320×568
  everyCell(844, { top: 0, bottom: 390 }, { left: 152, right: 844, top: 50, bottom: 350 });     // landscape, page scrolled
  everyCell(844, { top: 188, bottom: 390 }, { left: 152, right: 844, top: 238, bottom: 390 });  // landscape, page at the top
});

test('D3: a touch leaves no ring on a phone, a keyboard still does', () => {
  assert.match(css, /\.tb\.compact td:focus:not\(:focus-visible\) \{ outline: none; \}/);
  assert.match(css, /\.tb\.compact \{ -webkit-tap-highlight-color: transparent; \}/);
  assert.match(css, /\.tb td:focus, \.tb td:focus-visible \{ outline: 3px solid/);
});

test('D3: closing takes the mark', () => {
  assert.match(fn('closePicker'), /box\.remove\(\);\n\s+clearMark\(\);/);
});

test('D4: only a phone marks a score cell, and the mark moves with Next', () => {
  assert.match(fn('startEdit'), /if \(phone\) \{\n\s+markCell\(r, c\);/);
  assert.match(fn('closeEditor'), /if \(tb\.edit === ed\) \{[^}]*tb\.edit = null;\n\s+clearMark\(\);/);
});

test('D5: a click is held back whatever order the tap arrives in', () => {
  const click = fn('outsideClick');
  assert.match(click, /if \(outsideTap\) \{[^}]*closeOpen\(\);/);
  assert.match(fn('outsideUp'), /swallowUntil = Date\.now\(\) \+ TAP_CLICK_MS;\n\s+if \(Math\.hypot/);
  assert.match(fn('outsideCancel'), /if \(outsideTap\) swallowUntil = Date\.now\(\) \+ TAP_CLICK_MS;/);
});

// Mixes like color-mix(in srgb, a p%, b).
const hex = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));
const lum = (c) => {
  const [r, g, b] = c.map((x) => x / 255).map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

test('D1: text on the mark reaches 4.5:1, light and dark', () => {
  for (const from of [0, css.indexOf('prefers-color-scheme: dark')]) {
    const i = css.indexOf(':root', from);
    const body = css.slice(i, css.indexOf('}', i));
    const t = Object.fromEntries(Array.from(body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g), (m) => [m[1], m[2]]));
    const accent = hex(t.accent);
    const mark = hex(t.bg).map((x, k) => 0.82 * x + 0.18 * accent[k]);
    for (const name of ['text', 'muted', 'sec-1', 'sec-2', 'sec-3', 'sec-4']) {
      assert.ok(ratio(hex(t[name]), mark) >= 4.5, name + ' ' + ratio(hex(t[name]), mark).toFixed(2));
    }
  }
});
