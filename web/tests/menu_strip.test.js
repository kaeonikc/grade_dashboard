'use strict';
// Categories under the sections, the frozen top area and the phone score grid (SPEC_menu_strip.md).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const H = require('./helpers.js');

const read = (f) => fs.readFileSync(path.join(H.APPS, f), 'utf8');
const SRC = read('client_state.html').replace(/^<script>|<\/script>\s*$/g, '');
const VIEWS = read('client_views.html');
const css = H.readText(path.join(H.APPS, 'style.html'));

// client_state with course `folder` open.
function page(folder = H.F2) {
  const ctx = vm.createContext({
    Csv: H.Csv(), Grades: H.Grades(), Journal: H.Journal(), Save: H.Save(),
    google: { script: { run: {} } },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {}, length: 0, key: () => null },
    performance: { now: () => 0 }, document: { dispatchEvent() {} }, window: { addEventListener() {} },
    navigator: { onLine: true }, Event: class { constructor(t) { this.type = t; } }, console,
  });
  vm.runInContext(SRC, ctx, { filename: 'client_state.html' });
  const js = (code) => vm.runInContext(code, ctx);
  const state = js('state');
  state.open = { course: H.courseOf(folder) };
  return { js, state };
}

const list = (x) => JSON.parse(JSON.stringify(x));

test('plainName: one leading title comes off', () => {
  const { plainName } = H.Grades();
  assert.strictEqual(plainName('นางสาวกาลัญญ น้อยทู่'), 'กาลัญญ น้อยทู่');
  assert.strictEqual(plainName('นายสมชาย ใจดี'), 'สมชาย ใจดี');
  assert.strictEqual(plainName('นางสมศรี ใจดี'), 'สมศรี ใจดี');
  assert.strictEqual(plainName('น.ส.สมศรี ใจดี'), 'สมศรี ใจดี');
  assert.strictEqual(plainName('นาย สมชาย ใจดี'), 'สมชาย ใจดี', 'a space after the title goes too');
});

test('plainName: only one title, and only at the start', () => {
  const { plainName } = H.Grades();
  assert.strictEqual(plainName('นางสาวนายิกา ใจดี'), 'นายิกา ใจดี');
  assert.strictEqual(plainName('สมชาย นายดี'), 'สมชาย นายดี');
});

test('plainName: nothing to take off', () => {
  const { plainName } = H.Grades();
  assert.strictEqual(plainName('Somchai Jaidee'), 'Somchai Jaidee');
  assert.strictEqual(plainName('นาย'), 'นาย', 'a title alone stays');
  assert.strictEqual(plainName('นางสาว '), 'นางสาว ', 'a title alone stays');
  assert.strictEqual(plainName(''), '');
  assert.strictEqual(plainName(null), '');
});

test('modeOf: every Raw category is the grid; an open session is the session view', () => {
  const { js, state } = page();
  state.tab = 'raw';
  for (const category of ['homework', 'midterm', '*', 'attendance']) {
    state.category = category;
    state.attSession = false;
    assert.strictEqual(js('modeOf()'), 'table', category);
  }
  state.category = 'attendance';
  state.attSession = true;
  assert.strictEqual(js('modeOf()'), 'attendance');
  state.category = 'homework';
  assert.strictEqual(js('modeOf()'), 'table', 'attSession counts on attendance only');
  for (const tab of ['summary', 'analytics', 'grading']) {
    state.tab = tab;
    assert.strictEqual(js('modeOf()'), tab);
  }
});

test('catEntries: phone has no All columns and no points', () => {
  const { js, state } = page();
  const entries = list(js('catEntries(false)'));
  assert.deepStrictEqual(entries.map((e) => e.key), js('Grades').navCategories(state.open.course));
  assert.ok(entries.every((e) => e.pts == null));
});

test('catEntries: computer has All columns first, and points on the categories', () => {
  const { js, state } = page();
  const entries = list(js('catEntries(true)'));
  assert.deepStrictEqual(entries[0], { key: '*', label: 'All columns' });
  assert.deepStrictEqual(entries.slice(1).map((e) => e.key), js('Grades').navCategories(state.open.course));
  assert.ok(entries.slice(1).every((e) => typeof e.pts === 'number'));
});

test('tableColumns: no ID column on a phone, in every category', () => {
  const { js, state } = page();
  for (const category of ['homework', 'attendance']) {
    state.category = category;
    const phone = list(js('tableColumns(false)')).map((s) => s.kind);
    const wide = list(js('tableColumns(true)')).map((s) => s.kind);
    assert.strictEqual(phone[0], 'name', category);
    assert.ok(!phone.includes('id'), category);
    assert.deepStrictEqual(wide.slice(0, 2), ['id', 'name'], category);
    assert.deepStrictEqual(wide.slice(1), phone, category + ': the rest is the same');
  }
});

test('a score category ends with its computed total on a phone', () => {
  const { js, state } = page();
  state.category = 'homework';
  const specs = list(js('tableColumns(false)'));
  assert.deepStrictEqual(specs[specs.length - 1].cat, 'homework');
  assert.match(specs[specs.length - 1].label, /^homework \/\d/);
});

test('the ☰ menu is gone from the page', () => {
  for (const name of ['menuBtn', 'cm.menu', 'renderMenu', 'toggleMenu', 'closeDrawer', 'pickMenu', 'menuEntries',
    'cm.scrim']) {
    assert.ok(!VIEWS.includes(name), name);
  }
  for (const name of ['menuPref', 'rememberMenu', 'state.menu', 'MENU_KEY']) {
    assert.ok(!VIEWS.includes(name) && !SRC.includes(name), name);
  }
  assert.ok(!VIEWS.includes('☰') && !SRC.includes('☰'));
  for (const sel of ['.menu-btn', '.cat-menu', '.cat-item', '.scrim', '.menu-title', '.menu-list', 'menu-open']) {
    assert.ok(!css.includes(sel), sel);
  }
});

test('no column mode for scores is left', () => {
  assert.ok(!VIEWS.includes("'scores'") && !SRC.includes("'scores'"));
  assert.ok(!VIEWS.includes('viewColumns') && !VIEWS.includes('optionFor'));
});

// The declarations of the rule whose selector is exactly `selector`.
function rule(selector) {
  const m = new RegExp('(?:^|[}\\n])\\s*' + selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}').exec(css);
  assert.ok(m, 'style.html has a rule for ' + selector);
  return m[1];
}

test('the top area is a shaded panel with lines between its rows', () => {
  assert.match(rule('.top-panel'), /background:\s*var\(--bg2\)/);
  assert.match(rule('.top-panel'), /border-bottom:\s*2px solid/);
  assert.match(rule('.top-panel > * + *'), /border-top:\s*1px solid/);
});

test('section and category buttons are 2rem tall', () => {
  assert.match(rule('.sec-chip'), /min-height:\s*2rem/);
  assert.match(rule('.cat-chip'), /min-height:\s*2rem/);
});

test('section and category rows stay on one line and slide', () => {
  const r = rule('.sec-bar, .cat-bar');
  assert.match(r, /flex-wrap:\s*nowrap/);
  assert.match(r, /overflow-x:\s*auto/);
});

test('only the body of a course page scrolls', () => {
  assert.match(rule('main > .course-body'), /min-height:\s*0/);
  assert.match(rule('main:has(> .dock)'), /height:\s*100dvh/);
  assert.match(rule('main:has(> .dock)'), /overflow:\s*hidden/);
});

test("the grid's frozen cells stay under the student page", () => {
  assert.match(rule('.view-table .table-wrap'), /isolation:\s*isolate/);
});

test('typing in the grid hides the top area', () => {
  assert.match(rule('body.typing-grid .top-panel'), /display:\s*none/);
  assert.match(rule('body.typing-grid main'), /height:\s*var\(--typing-h/);
});

test('phone grid: smaller text, and no input under 16 px (iOS zooms on those)', () => {
  assert.match(rule('.tb.compact'), /font-size:\s*0\.875rem/);
  assert.match(rule('.tb.compact .c-name'), /font-size:\s*0\.8125rem/);
  assert.match(rule('.tb.compact .c-name .sub'), /font-size:\s*0\.6875rem/);
  assert.match(rule('.tb.compact .c-name'), /white-space:\s*normal/);
  assert.doesNotMatch(rule('.tb.compact .tb-input'), /font-size/);
  assert.doesNotMatch(rule('.tb-input'), /font-size/);
  assert.match(css, /button, input, select \{ font: inherit; font-size: max\(1rem, 16px\); \}/);
});

test('the text on the panel stays readable', () => {
  const hex = (name, from) => {
    const i = css.indexOf(':root {', from);
    return new RegExp('--' + name + ':\\s*(#[0-9a-fA-F]{6})').exec(css.slice(i, css.indexOf('}', i)))[1];
  };
  const lum = (h) => {
    const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
      .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a, b) => {
    const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
    return (x + 0.05) / (y + 0.05);
  };
  for (const from of [0, css.indexOf('prefers-color-scheme: dark')]) {
    for (const t of ['muted', 'accent', 'text']) {
      assert.ok(ratio(hex(t, from), hex('bg2', from)) >= 4.5, t + ' on --bg2');
    }
  }
});
