# grade_web: phone landscape (attendance grid disappears on rotation)

Status: approved 2026-10-20. Branch: `web-app`. Scope: `grade_dashboard/web/`. Builds on `SPEC_attendance_grid.md`.

## Context

The user reported that after rotating the iPhone (Safari) to landscape, Raw › attendance no longer shows the student
overview, and the only way to see a student is to search by ID or name. Safari's tab bar also appears in landscape and
takes more of the screen.

**Reproduced** in Playwright WebKit with iPhone 13 emulation:
- **The grid:** `.view-table main` is a fixed `height: 100vh` flex column. The grid box (`.table-wrap`, `flex: 1`) gets
  whatever height is left after the pinned header, search, grid toolbar and the bottom dock (Save plus the tab bar).
  - In portrait (664 px tall) that's 337 px.
  - In landscape it's 115 px (664×390), 65 px (844×340) and 25 px (750×300).
  - 65 px holds only the grid's own sticky header row and its sticky "Present" footer, so **no student row is
    visible**, which is exactly what the user sees.
  - The page itself can't scroll (fixed height), so Safari's bars never get a chance to collapse either.
- **Column mode, Summary and the session view:** these still scroll, but the pinned header (97 px) and the pinned dock
  (66 px with the tab bar, about 115 px with Save) leave about 175 px of 340 for students (2 rows).
- **The student detail:** its pinned bar and its pinned totals card take about 160 px in landscape.
- **What doesn't change:** state is unaffected by rotation (tab, category, column, search, edits and Grading inputs
  all survive). The 960 px wide breakpoint isn't crossed on any iPhone in landscape (844–932 px), so the layout stays
  in phone mode.
- **Text size:** iOS Safari also inflates text in landscape when `-webkit-text-size-adjust` isn't set. The user
  noticed text and layout changing.

The web app can't hide Safari's own tab bar. The fix is to stop wasting the height that's left.

## Decisions

| # | Decision |
|---|---|
| L1 | A **short screen** is `@media (max-height: 500px)`. It covers every phone in landscape (≤ 430 px tall) and leaves phones in portrait and iPads (≥ 744 px) alone. Pure CSS; no JS, no orientation events. |
| L2 | On a short screen the **course header scrolls away** (`.course-head` not sticky). The ☰, ‹, ⋯ and the unsaved badge come back when you scroll up. |
| L3 | **The grid (the `view-table` layout) on a short screen:** the page scrolls instead of being a fixed-height box. `main` gets `height: auto`, and the grid box gets `flex: none; height: calc(100dvh - 2.75rem)` (with a `100vh` fallback), so one swipe up gives the grid almost the whole screen: its sticky session header, frozen names and Present footer stay in place, and the rows scroll inside it. The 2.75 rem strip keeps a bit of toolbar or dock in view to swipe the page back. The dock is `position: static` here (under the grid). Save stays one swipe away, and the header badge comes back on scroll-up. |
| L4 | **The other phone views on a short screen:** column mode, the session view, Summary, Overview and Grading keep a pinned dock, but the phone tab bar shrinks to 44 px (`.tab` `min-height: 2.75rem`, still the WCAG 44 px touch target). |
| L5 | **The student detail on a short screen:** the totals card (`.det-card`) stops being pinned; the detail bar stays pinned. |
| L6 | **No text inflation on rotation:** `html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }`. This applies to all widths and is harmless on desktop. |
| L7 | The wide `view-table` height uses `100dvh` with a `100vh` fallback, as `main:has(> .dock)` already does. |

## Files

| File | Change |
|---|---|
| `web/apps_script/style.html` | Add L6 to the top rules. In L7, `.view-table main` gets `height: 100vh; height: 100dvh;`. Add a new block `/* 15. Short screens (phone landscape): SPEC_landscape.md */` with `@media (max-height: 500px)` rules for L2–L5. No new colour tokens, so `style.test.js` stays green. |
| `web/tests/style.test.js` | Add a small test: the stylesheet has a `@media (max-height: 500px)` block in which `.course-head` is `position: static` and `.view-table main` has `height: auto`, and `html` sets `text-size-adjust`. This guards against the rules being dropped. It reads `style.html` the way the existing contrast test does. |
| `web/SPEC.md`, `web/README.md` | Add a one-line pointer to `SPEC_landscape.md`. |
| memory `grade-web-app.md` | Add a line: check phone landscape (iPhone 13 at 844×340) in WebKit too. |

There are no JS changes. `client_views.html` and `client_state.html` are unchanged.

## Edge cases
- **Portrait phones, iPads and desktop windows taller than 500 px:** no change. A desktop window shorter than 500 px
  gets the short-screen layout, which is fine.
- **Rotating with the attendance picker open:** the picker is `position: absolute` inside the grid box, so it moves
  with its cell. Check it in the WebKit run.
- **Rotating while typing in column mode:** the keypad bar is pinned through `visualViewport` (`placeBar`), which is
  unchanged. With the header no longer pinned, more rows show above the keyboard.
- **The unsaved badge** isn't always on screen in landscape (it scrolls with the header). The dock's Save button is
  still reachable; in the grid it's one swipe away.
- **A course with a large grid (57 students × 14 sessions):** the grid box's own scrolling is unchanged.

## Out of scope
- Hiding Safari's own tab bar (websites can't). Home-screen standalone mode doesn't help either, because Apps Script
  pages are served inside Google's frame.
- Locking the orientation, layout changes for phones in portrait, and wide-screen (≥ 960 px) changes beyond L7.
- grade-tui, Python, and the server code.

## Verification (end to end)
1. **Automated** (from `grade_dashboard/`): `node --test 'web/tests/*.test.js' && python3 -m pytest tests/ -q &&
   cargo test --manifest-path rust_tui/Cargo.toml && web/scripts/e2e.sh`. All pass, and e2e ends `E2E OK`.
2. **WebKit rotation check** (scratchpad Playwright plus the preview harness, iPhone 13 emulation, F2):
   - **The grid in portrait (390×664):** about 337 px as before, with every row reachable.
   - **The grid in landscape (844×340 and 664×390):** after scrolling the page so the grid reaches the top, the grid
     box is at least 280 px tall at 844×340 and shows at least 4 student rows with their chips, the session header
     and the Present footer.
     - Tapping a cell, then A, edits it ("1 unsaved edit").
     - Scrolling down reaches Save.
   - **Rotating back to portrait:** restores the grid at about 337 px, and the state (tab, category, search,
     toggles, edits) is unchanged.
   - **Column mode, landscape:** the header scrolls away, and the tab bar is 44 px.
   - **Student detail, landscape:** the totals card isn't pinned.
   - Take screenshots of each, and look at them.
3. **Deploy:** `cd web && clasp push --force`, `clasp create-version`, then `clasp update-deployment <id> -V <N>`
   for both deployments. Check with `clasp list-deployments`.
4. **Phone:** the user opens Raw › attendance, rotates, and swipes up once. The whole grid should show. Rotating back
   should bring back the portrait layout. Leave without saving.
5. **Commit** locally on `web-app`: `fix(web): phone landscape keeps the attendance grid and more rows in view`.
