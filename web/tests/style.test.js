'use strict';
// style.html: grade colours reach 4.5:1 as text on --bg and --bg2, light and dark (SPEC_grade_order.md D6).
const test = require('node:test');
const assert = require('node:assert');
const H = require('./helpers.js');

const css = H.readText(require('node:path').join(H.APPS, 'style.html'));
const LETTERS = ['a', 'bp', 'b', 'cp', 'c', 'dp', 'd', 'f'];

// The custom properties of the first `:root {…}` at or after `from`.
function tokens(from) {
  const i = css.indexOf(':root {', from);
  const body = css.slice(i, css.indexOf('}', i));
  return Object.fromEntries(Array.from(body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g), (m) => [m[1], m[2]]));
}

function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

for (const [mode, from] of [['light', 0], ['dark', css.indexOf('prefers-color-scheme: dark')]]) {
  test('grade colours reach 4.5:1 in ' + mode, () => {
    assert.ok(from >= 0);
    const t = tokens(from);
    for (const g of LETTERS) {
      assert.ok(t['grade-' + g], mode + ' has --grade-' + g);
      for (const bg of ['bg', 'bg2']) {
        const r = contrast(t['grade-' + g], t[bg]);
        assert.ok(r >= 4.5, mode + ' --grade-' + g + ' on --' + bg + ': ' + r.toFixed(2));
      }
    }
  });
}

// Phone landscape (SPEC_landscape.md): the short-screen rules that keep the attendance grid in view.
test('short screens: header scrolls away, grid page scrolls, no text inflation', () => {
  const i = css.indexOf('@media (max-height: 500px)');
  assert.ok(i >= 0, 'has the short-screen block');
  const block = css.slice(i, css.indexOf('\n  }\n', i));
  assert.match(block, /\.course-head \{ position: static; \}/);
  assert.match(block, /\.view-table main \{ height: auto; \}/);
  assert.match(block, /\.view-table \.table-wrap \{[^}]*height: calc\(100dvh/);
  assert.match(css, /html \{[^}]*-webkit-text-size-adjust: 100%/);
});
