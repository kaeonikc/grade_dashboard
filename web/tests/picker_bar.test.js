'use strict';
// The marked cell and a phone's P/L/A/X bar (SPEC_picker_bar.md). client_views.html needs a browser, so here its shape
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

test('D2: a phone gets the bar beside the page, a computer the pop-up under its cell', () => {
  const open = fn('openPicker');
  assert.match(open, /if \(phone\) \{\n\s+box\.classList\.add\('picker-bar'\);\n\s+cm\.announce\.before\(box\);/);
  assert.match(open, /revealCell\(rec\.tds\[c\]\)/);
  assert.match(open, /\} else \{\n\s+cm\.wrap\.append\(box\);\n\s+place\(box, rec\.tds\[c\]\);/);
  assert.match(open, /focus\(\{ preventScroll: phone \}\)/);
});

test('D2: the bar is in the column, as wide as the screen, with 44 px buttons', () => {
  const bar = css.match(/\.tb-picker\.picker-bar \{([^}]+)\}/)[1];
  assert.match(bar, /position: static/);
  assert.match(bar, /margin: 0 -1rem/);
  const btn = css.match(/\.picker-bar \.btn \{([^}]+)\}/)[1];
  assert.match(btn, /flex: 1 1 0/);
  assert.match(btn, /min-width: 0/);
  assert.match(btn, /min-height: 2\.75rem/);
});

test('D2: a landscape phone keeps the bar on screen and the grid clear of it', () => {
  const short = css.slice(css.indexOf('@media (max-height: 500px)'), css.indexOf('/* 16. Sections'));
  assert.match(short, /\.tb-picker\.picker-bar \{ position: sticky; bottom: 0;/);
  assert.match(short, /\.view-table:has\(\.picker-bar\) \.table-wrap \{/);
  assert.match(fn('openPicker'), /window\.scrollBy\(0, under\)/);
});

test('D3: a touch leaves no ring on a phone, a keyboard still does', () => {
  assert.match(css, /\.tb\.compact td:focus:not\(:focus-visible\) \{ outline: none; \}/);
  assert.match(css, /\.tb\.compact \{ -webkit-tap-highlight-color: transparent; \}/);
  assert.match(css, /\.tb td:focus, \.tb td:focus-visible \{ outline: 3px solid/);
});

test('D3 and redraws: closing takes the mark, and no new table leaves a bar behind', () => {
  assert.match(fn('closePicker'), /box\.remove\(\);\n\s+clearMark\(\);/);
  assert.match(fn('renderTable'), /^function renderTable\(\) \{\n\s+closePicker\(\);/);
  assert.match(VIEWS, /if \(v !== 'table'\) \{\n\s+closePicker\(\);\n\s+tb = null;/);
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
