'use strict';
// Browser check for SPEC_picker_bar.md, on the preview server (server.js) over a scratch Drive copy.
//   PLAYWRIGHT=<dir of the playwright module> CHROME=<browser path> node picker_bar.js URL COURSE OUT_DIR
// COURSE is the course title on the first page. It has an attendance grid with a marked session 1 and empty session 2,
// and a homework column hw1. Exits 1 if a check fails.
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const [URL, COURSE, OUT] = process.argv.slice(2);
const TOUCH = { deviceScaleFactor: 2, isMobile: true, hasTouch: true };
const PHONE = { ...TOUCH, viewport: { width: 375, height: 665 } };
const SMALL = { ...TOUCH, viewport: { width: 320, height: 568 } };
const SIDE = { ...TOUCH, viewport: { width: 844, height: 390 } };
const WIDE = { viewport: { width: 1280, height: 800 } };
const CELLS = '.tb tbody tr:not(.sec-head):not(.tb-none):not([hidden]) td.c-code';

let bad = 0;
const check = (ok, what) => { console.log((ok ? 'ok   ' : 'FAIL ') + what); if (!ok) bad += 1; };
const wait = (p, ms = 300) => p.waitForTimeout(ms);

async function page(b, opts, section, category) {
  const c = await b.newContext(opts);
  const p = await c.newPage();
  p.on('pageerror', (e) => check(false, 'page error: ' + e.message));
  await p.goto(URL);
  await wait(p, 1500);
  await p.getByText(COURSE).first().click();
  await wait(p, 1300);
  await p.locator('.tabs .tab, .views .view-btn').filter({ hasText: 'Raw' }).filter({ visible: true }).first().click();
  await wait(p);
  await p.locator('.sec-chip').filter({ hasText: section }).first().click();
  await wait(p);
  await p.locator('.cat-chip').filter({ hasText: category }).first().click();
  await wait(p);
  return p;
}

// The `i`th student's cell in the grid's column `col` (0 = the first session).
const cellOf = (p, i, col) => p.evaluate(([sel, i, col]) => {
  const all = [...document.querySelectorAll(sel)];
  const perRow = all.filter((n) => n.parentElement === all[0].parentElement).length;
  const td = all[i * perRow + col];
  td.dataset.probe = '1';
  // The grid only: scrollIntoView would also move the page behind it, which a tap doesn't do.
  const w = document.querySelector('.table-wrap');
  const a = w.getBoundingClientRect();
  const b = td.getBoundingClientRect();
  w.scrollBy(b.left - (a.left + a.right) / 2 - 60, b.top - (a.top + a.bottom) / 2);
  return { r: td.dataset.r, c: td.dataset.c, last: Math.floor(all.length / perRow) - 1, perRow };
}, [CELLS, i, col]);

const tapAt = async (p, sel, n = 0) => {
  const box = await p.locator(sel).filter({ visible: true }).nth(n).boundingBox();
  await p.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2);
  await wait(p);
};
const tapCell = async (p, i, col) => {
  const at = await cellOf(p, i, col);
  const sel = `td[data-r="${at.r}"][data-c="${at.c}"]`;
  await tapAt(p, sel);
  return { ...at, sel };
};

// What the screen shows of the open pop-up and its cell.
const seen = (p, sel) => p.evaluate((sel) => {
  const td = document.querySelector(sel);
  const r = td.getBoundingClientRect();
  const box = document.querySelector('.tb-picker');
  const b = box && box.getBoundingClientRect();
  const name = document.querySelector('thead .c-name').getBoundingClientRect();
  const foot = document.querySelector('.att-foot td');
  const present = foot && foot.getBoundingClientRect();
  const wrap = document.querySelector('.table-wrap').getBoundingClientRect();
  const hit = document.elementFromPoint(Math.min(r.left + r.width / 2, innerWidth - 1), r.top + r.height / 2);
  return {
    box: !!box, grid: !!box && box.classList.contains('picker-grid'),
    x: b && b.left, right: b && b.right, y: b && b.top, end: b && b.bottom, w: b && b.width, h: b && b.height,
    buttons: box ? [...box.querySelectorAll('button')].map((n) => [n.getBoundingClientRect().width, n.getBoundingClientRect().height]) : [],
    width: innerWidth, height: innerHeight, sideScroll: document.documentElement.scrollWidth > innerWidth,
    wrapTop: wrap.top, wrapBottom: wrap.bottom, rowsTop: name.bottom, rowsBottom: present ? present.top : wrap.bottom, nameRight: name.right,
    top: r.top, bottom: r.bottom, left: r.left, cellRight: r.right,
    clear: !b || !(b.left < r.right && r.left < b.right && b.top < r.bottom && r.top < b.bottom),
    onTop: !!hit && td.contains(hit),
    picked: document.querySelectorAll('td.picked').length,
    cellPicked: td.classList.contains('picked'),
    lines: [...document.querySelectorAll('.pick-line')].map((n) => n.tagName + '.' + n.className.split(' ')[0]),
    ring: getComputedStyle(td).outlineStyle !== 'none',
    active: document.activeElement.tagName,
  };
}, sel);

// Where every row and the grid's scroll stand: unchanged means nothing moved under the finger.
const rowsAt = (p) => p.evaluate(() => JSON.stringify({
  y: [...document.querySelectorAll('.tb tbody tr')].map((n) => n.getBoundingClientRect().top),
  x: document.querySelector('.tb tbody td.c-code').getBoundingClientRect().left,
  top: document.querySelector('.table-wrap').scrollTop,
  page: [scrollY, document.querySelector('main').scrollTop],
}));

const clean = (p) => p.evaluate(() => ({
  box: !!document.querySelector('.tb-picker'),
  marks: document.querySelectorAll('.picked, .pick-line').length,
  rings: [...document.querySelectorAll('.tb td')].filter((n) => getComputedStyle(n).outlineStyle !== 'none').length,
  input: !!document.querySelector('.tb-input'),
  detail: !!document.querySelector('.detail'),
  dialog: !!document.querySelector('dialog[open]'),
  keyboard: document.activeElement.tagName === 'INPUT',
  sec: document.querySelector('.sec-chip[aria-pressed="true"]').innerText,
  cat: document.querySelector('.cat-chip[aria-pressed="true"]').innerText,
  tab: [...document.querySelectorAll('.tab')].filter((n) => n.getAttribute('aria-pressed') === 'true').map((n) => n.innerText).join(),
  save: !!document.querySelector('.save-btn:not([hidden])'),
  unsaved: document.querySelectorAll('.tb td.unsaved').length,
}));

async function onlyCloses(p, what, sel, n) {
  await tapCell(p, 3, 1);
  const before = await clean(p);
  await tapAt(p, sel, n);
  const after = await clean(p);
  check(before.box && !after.box && after.marks === 0 && after.rings === 0, what + ': closes, no mark or ring');
  check(!after.detail && !after.dialog && !after.input && !after.keyboard, what + ': nothing else opens');
  check(after.sec === before.sec && after.cat === before.cat && after.tab === before.tab, what + ': same view');
  check(after.unsaved === before.unsaved, what + ': no value changed');
}

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || undefined });

  // ---- Phone: the grid and the mark ----
  let p = await page(b, PHONE, 'All', 'attendance');
  let at = await tapCell(p, 8, 1);
  let s = await seen(p, at.sel);
  await p.screenshot({ path: path.join(OUT, '1_grid.png') });
  console.log(JSON.stringify(s));
  check(s.grid, 'phone: P/L/A/X is the floating grid');
  check(s.buttons.length === 5 && s.buttons.slice(0, 4).every(([w, h]) => w >= 36 && h >= 36), 'P/L/A/X are 36 px: ' + s.buttons);
  check(s.w <= 80 && s.h <= 108, 'the grid is small: ' + s.w + '×' + s.h);
  check(s.cellPicked && s.picked === 1, 'the cell is marked');
  check(s.ring, 'the cell has its outline');
  check(s.lines.length === 2 && s.lines.some((l) => l.startsWith('TH')) && s.lines.some((l) => l.includes('c-name')),
    'name and head are marked: ' + s.lines);
  check(s.active === 'BUTTON', 'focus is on the grid');
  check(s.onTop && s.clear, 'nothing covers the cell');
  check(s.x >= s.nameRight, 'the grid leaves the names alone');
  check(Math.abs(s.x - s.cellRight) <= 8 || Math.abs(s.right - s.left) <= 8, 'the grid is beside the cell');

  // The rows don't move: from a fully shown cell, cells cut off at each edge, on open, pick and close
  const still = async (what, setup, act) => {
    const q = await setup();
    const before = await rowsAt(p);
    await act(q);
    check(await rowsAt(p) === before, what + ': the rows stay put');
  };
  await tapAt(p, 'thead .c-name');
  // Puts a cell with `edge` of it cut off by the head, the Present line or the right side, and returns its selector.
  const cutOff = (edge) => async () => {
    const sel = await p.evaluate(([cells, edge]) => {
      const w = document.querySelector('.table-wrap');
      const head = document.querySelector('thead .c-name').getBoundingClientRect();
      const foot = document.querySelector('.att-foot td').getBoundingClientRect();
      const pos = (n) => n.getBoundingClientRect();
      w.scrollLeft = 0;
      const all = [...document.querySelectorAll(cells)];
      const perRow = all.filter((n) => n.parentElement === all[0].parentElement).length;
      const td = all[20 * perRow + (edge === 'right' ? 4 : 2)];  // a session with nothing marked yet
      if (edge === 'top') w.scrollBy(0, pos(td).top - head.bottom + 12);
      if (edge === 'bottom') w.scrollBy(0, pos(td).bottom - foot.top - 12);
      if (edge === 'right') w.scrollBy(pos(td).right - w.getBoundingClientRect().right - 16, pos(td).top - 350);
      return `td[data-r="${td.dataset.r}"][data-c="${td.dataset.c}"]`;
    }, [CELLS, edge]);
    await wait(p, 100);
    return sel;
  };
  const tapPart = (edge) => async (sel) => {
    const r = await p.locator(sel).boundingBox();
    const px = { top: [r.x + r.width / 2, r.y + r.height - 5], bottom: [r.x + r.width / 2, r.y + 5], right: [r.x + 5, r.y + r.height / 2] }[edge];
    await p.touchscreen.tap(px[0], px[1]);
    await wait(p);
  };
  for (const edge of ['top', 'bottom', 'right']) {
    await still('cell cut off at the ' + edge + ', open', cutOff(edge), tapPart(edge));
    check(await p.locator('.tb-picker').count() === 1, 'cell cut off at the ' + edge + ': the grid opens');
    await still('cell cut off at the ' + edge + ', P', async () => {}, () => tapAt(p, '.picker-grid .code-P'));
    await still('cell cut off at the ' + edge + ', Clear', async () => {
      const sel = await cutOff(edge)();
      await tapPart(edge)(sel);
    }, () => tapAt(p, '.picker-grid .btn.outline'));
    await still('cell cut off at the ' + edge + ', tap outside', async () => {
      const sel = await cutOff(edge)();
      await tapPart(edge)(sel);
    }, () => tapAt(p, 'thead .c-name'));
    await wait(p, 800);
  }
  await p.context().close();
  p = await page(b, PHONE, 'All', 'attendance');
  at = await tapCell(p, 8, 1);

  // Every session and row: on screen, off the cell, off the names
  await tapAt(p, 'thead .c-name');
  await wait(p, 800);
  for (const [name, r, col] of [['first row', 0, 1], ['second-last session', 2, 12], ['last session', 4, 13], ['middle', 10, 5], ['last row', 54, 1], ['last row, last session', 54, 13]]) {
    at = await tapCell(p, r, col);
    s = await seen(p, at.sel);
    check(s.box && s.clear && s.x >= s.nameRight - 1 && s.right <= s.width && s.y >= s.wrapTop && s.end <= s.wrapBottom,
      name + ': the grid is on screen, off the cell and the names');
    if (r === 54) await p.screenshot({ path: path.join(OUT, '2_last_row.png') });
    if (col === 13 && r === 4) await p.screenshot({ path: path.join(OUT, '3_last_session.png') });
    await tapAt(p, 'thead .c-name');
    await wait(p, 800);
  }

  // Scrolling isn't a tap
  at = await tapCell(p, 8, 1);
  const wrap = await p.locator('.table-wrap').boundingBox();
  await p.evaluate(() => document.querySelector('.table-wrap').scrollBy(0, 120));
  await wait(p, 150);
  check((await clean(p)).box, 'scrolling leaves the grid open');
  await p.context().close();

  // Drag with a real touch: dispatch through CDP, as a finger would
  p = await page(b, PHONE, 'All', 'attendance');
  at = await tapCell(p, 8, 1);
  const cdp = await p.context().newCDPSession(p);
  const finger = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
  const x = wrap.x + 150; const y = wrap.y + 200;
  const scrollBefore = await p.evaluate(() => document.querySelector('.table-wrap').scrollTop);
  await finger('touchStart', x, y);
  for (let i = 1; i <= 8; i += 1) { await finger('touchMove', x, y - i * 12); await wait(p, 16); }
  await finger('touchEnd');
  await wait(p);
  const scrollAfter = await p.evaluate(() => document.querySelector('.table-wrap').scrollTop);
  const dragged = await clean(p);
  check(scrollAfter !== scrollBefore && dragged.box && dragged.marks === 3, 'a finger drag scrolls and the grid stays');
  await p.context().close();

  p = await page(b, PHONE, 'All', 'attendance');

  // ---- Phone: a tap outside only closes ----
  await onlyCloses(p, 'another cell', 'td[data-r="1"][data-c]', 1);
  await onlyCloses(p, 'a name', 'td[data-r="1"].c-name');
  await onlyCloses(p, 'the marked cell', 'td.picked');
  await onlyCloses(p, 'a section chip', '.sec-chip', 1);
  await onlyCloses(p, 'a category chip', '.cat-chip', 1);
  await onlyCloses(p, 'a tab', '.tabs .tab', 0);
  await onlyCloses(p, 'a session head', '.att-head', 1);
  await onlyCloses(p, 'the search box', '.search-input');
  await onlyCloses(p, 'the Present row', '.att-foot td');

  // A second tap acts as usual
  await tapCell(p, 3, 1);
  await tapAt(p, 'td[data-r="1"].c-name');
  await wait(p, 800);
  await tapCell(p, 2, 1);
  check((await clean(p)).box, 'after a close, the next tap opens a cell');
  await tapAt(p, 'thead .c-name');

  // Event orders a real tap may use: the click must never reach the cell under the finger
  let c;
  const events = (kinds, moved) => p.evaluate(([kinds, moved]) => {
    const td = document.querySelector('td[data-r="1"].c-name');
    const r = td.getBoundingClientRect();
    const at = (x) => ({ bubbles: true, cancelable: true, clientX: r.left + 5 + x, clientY: r.top + 5, pointerId: 1 });
    for (const k of kinds) {
      td.dispatchEvent(k === 'click' ? new MouseEvent('click', at(0))
        : new PointerEvent(k, at(k === 'pointerdown' ? 0 : moved)));
    }
  }, [kinds, moved]);
  await tapCell(p, 3, 1);
  await events(['pointerdown', 'click', 'pointerup'], 0);
  await wait(p);
  c = await clean(p);
  check(!c.box && !c.detail && c.marks === 0, 'a click before its pointerup only closes');
  await tapCell(p, 3, 1);
  await events(['pointerdown', 'pointerup', 'click'], 30);
  await wait(p);
  c = await clean(p);
  check(c.box && !c.detail, 'a drag that still clicks: the grid stays, nothing opens');
  await tapAt(p, 'thead .c-name');
  await tapCell(p, 3, 1);
  await events(['pointerdown', 'pointercancel', 'click'], 0);
  await wait(p);
  c = await clean(p);
  check(c.box && !c.detail, 'a cancelled press that still clicks: the grid stays, nothing opens');
  await tapAt(p, 'thead .c-name');
  await wait(p, 800);

  // Picking
  at = await tapCell(p, 5, 1);
  await tapAt(p, '.picker-grid .code-P');
  c = await clean(p);
  check(!c.box && c.marks === 0 && c.rings === 0, 'P: the grid closes, no mark or ring');
  check(c.unsaved === 1 && /^P/.test((await p.locator(at.sel).innerText()).trim()), 'P: the cell holds P, unsaved');
  at = await tapCell(p, 5, 1);
  check(await p.locator('.picker-grid .code-P').getAttribute('aria-pressed') === 'true', 'the grid shows the cell\'s code');
  await tapAt(p, '.picker-grid .btn.outline');
  c = await clean(p);
  check(!c.box && c.unsaved === 0, 'Clear: the cell is back to empty');

  // Redrawing the grid closes the bar
  await tapCell(p, 3, 1);
  await p.evaluate(() => { renderTable(); });
  await wait(p);
  c = await clean(p);
  check(!c.box && c.marks === 0, 'a new table takes the grid and the mark away');
  await p.setViewportSize({ width: 1100, height: 800 });
  await wait(p);
  await p.setViewportSize({ width: 375, height: 665 });
  await wait(p);
  await tapCell(p, 3, 1);
  await p.setViewportSize({ width: 1100, height: 800 });
  await wait(p);
  check(!(await clean(p)).box, 'crossing 960 px closes the grid');
  await p.context().close();

  // ---- Phone: typing a score ----
  p = await page(b, PHONE, 'Sec 51', 'homework');
  await tapAt(p, 'td[data-r="1"].c-score');
  s = await seen(p, 'td[data-r="1"].c-score');
  check(s.cellPicked && s.lines.length === 2, 'score cell: marked while typing');
  await p.screenshot({ path: path.join(OUT, '4_score.png') });
  await p.locator('.kbar-next').click();
  await wait(p);
  check(await p.locator('td[data-r="2"].c-score').first().evaluate((n) => n.classList.contains('picked')), 'Next ↓ takes the mark along');
  check(await p.locator('td.picked').count() === 1, 'one mark after Next ↓');
  await tapAt(p, 'thead .c-name');
  await wait(p, 300);
  check((await p.locator('.picked, .pick-line').count()) === 0, 'the mark ends with the typing');
  await p.context().close();

  // ---- 320 px and landscape ----
  p = await page(b, SMALL, 'All', 'attendance');
  at = await tapCell(p, 6, 1);
  s = await seen(p, at.sel);
  await p.screenshot({ path: path.join(OUT, '5_320.png') });
  console.log(JSON.stringify(s));
  check(s.right <= 320 && !s.sideScroll && s.clear, '320 px: the grid fits and the cell shows');
  for (const [r, col] of [[9, 2], [10, 3], [11, 1]]) {
    await tapAt(p, 'thead .c-name');
    await wait(p, 800);
    at = await tapCell(p, r, col);
    s = await seen(p, at.sel);
    check(s.box && s.clear && s.x >= s.nameRight - 1 && s.right <= 320 && s.y >= s.wrapTop && s.end <= s.wrapBottom, '320 px, column ' + col + ': the grid is clear');
  }
  const clear = await p.locator('.picker-grid .btn.outline').evaluate((n) => n.scrollWidth <= n.clientWidth);
  check(clear, '320 px: Clear fits its button');
  await p.context().close();

  p = await page(b, SIDE, 'All', 'attendance');
  at = await tapCell(p, 8, 1);
  s = await seen(p, at.sel);
  await p.screenshot({ path: path.join(OUT, '6_landscape.png') });
  console.log(JSON.stringify(s));
  check(s.grid && s.end <= s.height + 1 && s.y >= 0, 'landscape: the grid is on screen');
  check(s.clear && s.x >= s.nameRight - 1, 'landscape: the grid is off the cell and the names');
  await p.context().close();

  // ---- Computer ----
  p = await page(b, WIDE, 'All', 'attendance');
  await p.locator('td.c-code').nth(20).click();
  await wait(p);
  s = await seen(p, 'td.picked');
  await p.screenshot({ path: path.join(OUT, '7_wide.png') });
  check(s.box && !s.grid, 'computer: the pop-up is the row of buttons');
  check(s.y >= s.bottom - 1 && s.y <= s.bottom + 1, 'computer: under its cell');
  check(s.cellPicked && s.lines.length === 2, 'computer: marked');
  await p.keyboard.press('Escape');
  await wait(p);
  c = await clean(p);
  check(!c.box && c.marks === 0 && c.rings === 1, 'Esc: closes, the keyboard ring stays on the cell');
  await p.keyboard.press('p');
  await wait(p);
  check((await clean(p)).unsaved === 1, 'P key still marks');
  await p.locator('td.c-code').nth(30).click();
  await wait(p);
  await p.locator('td.c-code').nth(40).click();
  await wait(p);
  c = await clean(p);
  check(!c.box && c.marks === 0, 'a click outside closes');
  await p.context().close();

  p = await page(b, WIDE, 'Sec 51', 'homework');
  await p.locator('td.c-score').first().dblclick();
  await wait(p);
  check((await p.locator('td.picked').count()) === 0, 'computer typing: no mark');
  await p.keyboard.press('Escape');
  await p.context().close();

  // ---- Dark ----
  p = await page(b, { ...PHONE, colorScheme: 'dark' }, 'All', 'attendance');
  await tapCell(p, 8, 1);
  await p.screenshot({ path: path.join(OUT, '8_dark.png') });
  await p.context().close();

  await b.close();
  console.log(bad ? 'FAILED: ' + bad : 'ALL OK');
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
