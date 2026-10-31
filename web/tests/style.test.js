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

// Bar fills: grade-tui's hues, softened (SPEC_bar_colours.md B1-B4): bars only, an edge in the letter colour in light mode.
const BARS = { a: '#2772c6', bp: '#2ca2a2', b: '#5aac47', cp: '#a4c34b', c: '#e4d457', dp: '#e8a634', d: '#de7b21',
  f: '#bd3a2e' };
const DARK = css.indexOf('prefers-color-scheme: dark');
const edge = (from) => {
  const i = css.indexOf(':root {', from);
  return (css.slice(i, css.indexOf('}', i)).match(/--bar-edge:\s*([^;]+);/) || [])[1];
};

test('bar fills are the palette swatches, shared by light and dark', () => {
  const light = tokens(0);
  for (const g of LETTERS) assert.strictEqual(light['bar-' + g], BARS[g], '--bar-' + g);
  for (const g of LETTERS) assert.ok(!('bar-' + g in tokens(DARK)), 'dark keeps the light --bar-' + g);
});

test('light bars have a 1px edge in a letter colour reaching 3:1; dark bars have none and their fills reach 3:1', () => {
  const [light, dark] = [tokens(0), tokens(DARK)];
  assert.strictEqual(edge(0), '1px');
  assert.strictEqual(edge(DARK), '0');
  for (const g of LETTERS) {
    const r = contrast(light['grade-' + g], light.bg2);
    assert.ok(r >= 3, 'light edge --grade-' + g + ': ' + r.toFixed(2));
    const f = contrast(BARS[g], dark.bg2);
    assert.ok(f >= 3, 'dark fill --bar-' + g + ': ' + f.toFixed(2));
  }
});

test('a grade bar is filled from its --bar token and edged with currentColor; histogram bars have no edge', () => {
  assert.match(css, /\.dist \.bar span \{[^}]*background: var\(--bar-fill, currentColor\)/);
  assert.match(css, /\.dist \.bar span \{[^}]*box-shadow: inset 0 0 0 var\(--bar-edge\) currentColor/);
  for (const g of LETTERS) {
    assert.match(css, new RegExp('\\.dist \\.bar \\.g-' + g + ' \\{ --bar-fill: var\\(--bar-' + g + '\\); \\}'), g);
  }
  assert.match(css, /\.dist \.bar span\.plain \{[^}]*box-shadow: none/);
});

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

// Section colours (SPEC_sections.md): names and IDs as text on --bg, --bg2 and the ID chip's 14% tint, and --bg as
// the text of a pressed chip, all >= 4.5:1.
function mix(a, b, w) {
  const ch = (h, i) => parseInt(h.slice(i, i + 2), 16);
  return '#' + [1, 3, 5].map((i) => Math.round(ch(a, i) * w + ch(b, i) * (1 - w)).toString(16).padStart(2, '0')).join('');
}

for (const [mode, from] of [['light', 0], ['dark', css.indexOf('prefers-color-scheme: dark')]]) {
  test('section colours reach 4.5:1 in ' + mode, () => {
    const t = Object.assign(tokens(0), tokens(from));
    for (const k of [1, 2, 3, 4]) {
      const sec = t['sec-' + k];
      assert.ok(sec, mode + ' has --sec-' + k);
      for (const bg of [t.bg, t.bg2, mix(sec, t.bg, 0.14)]) {
        const r = contrast(sec, bg);
        assert.ok(r >= 4.5, mode + ' --sec-' + k + ' on ' + bg + ': ' + r.toFixed(2));
      }
    }
  });
}

// SPEC_name_stripes.md: full names in the grids (N1, N2) and striped rows that stay readable (N3).
// The declarations of the rule whose selector is exactly `selector`.
function rule(selector) {
  const m = new RegExp('(?:^|[}\\n])\\s*' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}').exec(css);
  assert.ok(m, 'style.html has a rule for ' + selector);
  return m[1];
}

test('phone grid: the name wraps in a 10.5rem column, never cut', () => {
  const r = rule('.att-grid.compact .c-name');
  assert.match(r, /white-space:\s*normal/);
  assert.match(r, /\bwidth:\s*10\.5rem/);
  assert.match(r, /min-width:\s*10\.5rem/);
  assert.match(r, /max-width:\s*10\.5rem/);
  assert.doesNotMatch(r, /ellipsis/);
});

test('wide table: the name column fits the longest name on one line', () => {
  const r = rule('.tb .c-name');
  assert.match(r, /min-width:\s*13rem/);
  assert.match(r, /max-width:\s*none/);
  assert.doesNotMatch(r, /ellipsis|overflow:\s*hidden/);
});

// `hex` washed at `p` over `bg`, as color-mix(in srgb, hex p, transparent) painted over bg.
function wash(hex, bg, p) {
  const ch = (h, i) => parseInt(h.slice(i, i + 2), 16);
  return '#' + [1, 3, 5].map((i) => Math.round(ch(hex, i) * p + ch(bg, i) * (1 - p)).toString(16).padStart(2, '0'))
    .join('');
}

for (const [mode, from] of [['light', 0], ['dark', css.indexOf('prefers-color-scheme: dark')]]) {
  test('text on a striped row reaches 4.5:1 in ' + mode, () => {
    // --stripe over plain cells (--bg), the lighter --stripe-grey over computed ones (--bg2)
    const pct = (name) => {
      const m = new RegExp('--' + name + ':\\s*color-mix\\(in srgb, var\\(--sec, var\\(--accent\\)\\) (\\d+)%, transparent\\)').exec(css);
      assert.ok(m, 'style.html defines --' + name);
      return +m[1] / 100;
    };
    const p = { bg: pct('stripe'), bg2: pct('stripe-grey') };
    const t = tokens(from);
    const inks = ['text', 'muted', 'danger'].concat(LETTERS.map((g) => 'grade-' + g));
    for (const hue of ['sec-1', 'sec-2', 'sec-3', 'sec-4', 'accent']) {
      for (const bg of ['bg', 'bg2']) {
        const under = wash(t[hue], t[bg], p[bg]);
        for (const ink of inks.concat(hue.startsWith('sec') ? [hue] : [])) {
          const r = contrast(t[ink], under);
          assert.ok(r >= 4.5, mode + ' --' + ink + ' on a --' + hue + ' stripe over --' + bg + ': ' + r.toFixed(2));
        }
      }
    }
  });
}
