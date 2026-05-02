# Workout Chart Compliance Redesign — Design Spec

**Date:** 2026-05-02
**Status:** Approved
**Supersedes:** Sections "Power Row" and "Segment Labels Row" of `2026-05-02-run-holistic-visualization-design.md`

---

## Context

The first implementation of the holistic workout chart (per the spec above) used coloured fills to represent compliance — green fill for in-range, orange layered on top for above, red for below. After seeing this with real data, the problem is that the fill colour conflates two distinct things: the *position* of the average (watts) and the *distribution* of time. A segment where the average sits just inside the band but most time was spent out of zone looks identical to a well-executed one. The redesign separates these into two distinct visual elements: a neutral power bar with a coloured avg line showing position, and a dedicated compliance strip below it showing time distribution.

---

## What Changes

The changes are confined to `runcoach/web/templates/run_detail.html`. No backend changes are needed — the data model is unchanged. The CSS classes for the power bar and the new compliance strip are updated; everything else (tooltip, HR strip, column widths, tests) follows the existing patterns.

### Removed from the power bar
- Coloured fill (green / orange / red based on compliance)
- Compliance badge text (`85% in zone`, `47% above`, etc.)

### Changed in the power bar
- Fill is now **always** the same faint neutral (`rgba(255,255,255,0.04)`) — just a height reference
- Target band styling: stronger contrast — `rgba(255,255,255,0.11)` fill, `rgba(255,255,255,0.38)` top/bottom borders (was `rgba(255,255,255,0.06)` fill / `rgba(255,255,255,0.2)` borders)
- Avg power line colour encodes compliance position (see below)

### Added
- **Compliance strip** — a new row between the power bar and the HR strip
- **Z1–Z5 labels** inside each HR zone slice, conditionally shown via CSS container queries

### Changed: column separators
- Replace the `border-right: 1px solid #21262d` vertical divider with a `gap: 6px` on the column grid

### Changed: segment labels
- All segment names are a single neutral colour `#8b949e` — no type-based colouring

---

## Power Bar (revised)

**Fill:** `rgba(255,255,255,0.04)`, full width, height = `avg_power / power_scale_max * 100%`. Always rendered regardless of compliance state — purely for height context.

**Target band** (when `target_power` exists): absolute-positioned rectangle from `min_w` to `max_w` on the watts scale.
- Fill: `rgba(255,255,255,0.11)`
- Border top + bottom: `1px solid rgba(255,255,255,0.38)`

**Avg power line:** 2px horizontal rule at the `avg_power` position. Colour encodes compliance against the target:

| State | Condition | Colour | Glow |
|---|---|---|---|
| In range | `min_w ≤ avg_power ≤ max_w` | `#00e676` (green) | `0 0 7px 1px rgba(0,230,118,0.75), 0 0 14px rgba(0,230,118,0.4)` |
| Above | `avg_power > max_w` | `#ff3d71` (red/pink) | `0 0 7px 1px rgba(255,61,113,0.75), 0 0 14px rgba(255,61,113,0.4)` |
| Below | `avg_power < min_w` | `#2979ff` (blue) | `0 0 7px 1px rgba(41,121,255,0.75), 0 0 14px rgba(41,121,255,0.4)` |
| No target | no `target_power` | `#6e7681` (grey) | none |

**Avg watts label:** Right-aligned, positioned just above the avg line (`bottom: calc(<avg_pct>% + 3px)`). Hidden when the column is narrower than 40px (JS `offsetWidth` check, same mechanism as the existing implementation).

---

## Compliance Strip (new)

A new row inserted **between** the power bar and the HR strip. Height 20px. Border-radius 10px (pill shape).

When `target_power` exists: three adjacent colour blocks, left to right:
- **Below** (blue): `rgba(41,121,255,0.7)`, width = `pct_time_below %`
- **In** (green): `rgba(0,230,118,0.6)`, width = `pct_time_in_range %`
- **Above** (red): `rgba(255,61,113,0.7)`, width = `pct_time_above %`

When no `target_power`: single block `#1c2128` with centred text "no target" (`color: #444d56; font-size: 0.6rem`).

Border: `1px solid #30363d` on the container. `overflow: hidden` so the pill shape clips the inner blocks.

---

## HR Strip (updated)

No structural change. Two additions:

1. **Height:** Increase from 18px to 22px to accommodate labels.
2. **Z-labels:** Each zone slice (`<div class="wc-hz ...">`) wraps a `<span>` containing its zone name (`Z1`, `Z2`, etc.). The span is shown or hidden based on whether its slice is wide enough:
   ```css
   .wc-hz {
     container-type: inline-size;
   }
   .wc-hz span { display: none; }
   @container (min-width: 20px) {
     .wc-hz span { display: block; }
   }
   ```
   Label style: `font-size: 0.5rem; font-weight: 700; color: rgba(255,255,255,0.8); text-shadow: 0 1px 2px rgba(0,0,0,0.6)`.
3. **Border-radius:** 10px (pill shape, `overflow: hidden` clips zone slices to the rounded container).

---

## Column Separators

Replace the per-column `border-right: 1px solid #21262d` with `gap: 6px` on `.wc-grid`. Use `flex: 1 0 <pct>%` (allow shrink) on each column instead of `flex: 0 0 <pct>%` so flexbox distributes the gap space proportionally across all columns while preserving relative widths. The pill-shaped strips provide enough visual separation that hard dividers are not needed.

---

## Segment Labels

All segment names use `#8b949e` (neutral grey). The type-based colouring (warmup blue, work green/orange/red) is removed — the avg power line and compliance strip already communicate compliance state; colouring the label redundantly is visual noise.

---

## Legend (updated)

Replace existing legend entries with:
- Target range: white band swatch
- Avg — in target: green glowing line
- Avg — too high: red/pink glowing line
- Avg — too low: blue glowing line
- % time in zone: green swatch
- % time above: red swatch
- % time below: blue swatch

---

## Containment

The chart must never overflow its card or the browser viewport width. Requirements:

- `.wc-grid` must have `width: 100%` and `overflow: hidden` — the column flex items must not push beyond the card boundary
- Each `.wc-col` must have `min-width: 0` in addition to the existing `min-width: 28px` floor — this prevents flex items from overflowing when their content (watts label, segment name) is wider than the column; the `min-width: 28px` floor should be applied as a `max(28px, ...)` in Jinja or handled by clamping the flex-basis
- All inner elements (power bar, compliance strip, HR strip, segment name) must use `width: 100%` and not have fixed pixel widths that could cause overflow
- The `.chart-card` (or equivalent card wrapper) must have `overflow: hidden` or at minimum `max-width: 100%` to act as a containment boundary

On very narrow screens where even 28px columns would overflow (e.g. a workout with 8+ segments on a 320px screen), the chart may scroll horizontally within the card (`overflow-x: auto` on `.wc-grid`) rather than breaking the page layout.

---

## Responsive Behaviour

No change from the existing spec. The compliance strip height (20px) and HR strip height (22px) are fixed regardless of breakpoint — only the power bar height changes (130px desktop, 90px mobile).

---

## Impact on Tests

### Unit tests (`tests/test_web.py` — `TestWorkoutChart`)

The two existing tests check for class names in the rendered HTML. These need updating:

- `test_workout_chart_renders_with_targets`:
  - Add assertion: `assert "comp-strip" in html` (compliance strip row present)
  - Add assertion: `assert "cs-in" in html` (in-range colour block present)
  - Remove assertion: `assert "wc-fill--in" in html` (class no longer exists — fill is always neutral)
- `test_workout_chart_no_targets_renders`:
  - Add assertion: `assert "cs-none" in html` (no-target placeholder present)
  - Remove assertion: `assert "wc-fill--none" in html` (class no longer exists — fill is always neutral)

### E2E tests (`tests/e2e/test_workout_chart.py`)

No structural changes needed — the tooltip, grid, column, and power bar elements are still present with the same class names. Existing tests should continue to pass without modification.

---

## Verification

1. Load a run with a segment where `avg_power` is within range — confirm avg line is green with glow, compliance strip shows mostly green, power bar fill is neutral faint white
2. Load a run with a segment where `avg_power > max_w` — confirm red/pink avg line, compliance strip shows significant red on right
3. Load a run with a segment where `avg_power < min_w` — confirm blue avg line, compliance strip shows significant blue on left
4. Load a run with no power targets — confirm grey avg lines, compliance strip shows "no target" placeholder
5. Verify target band is visibly brighter than in the previous implementation
6. Hover each segment — tooltip content unchanged; running dynamics where present
7. Confirm HR labels appear in wide-enough slices and are absent in narrow ones (e.g. a 4% Z2 slice on `work_2` should show no label)
8. Resize to ~375px — pill shapes still visible, no overflow, labels truncate gracefully
9. Run `pytest tests/test_web.py::TestWorkoutChart -v` — both tests pass
10. Run `pytest -m e2e --no-cov -v tests/e2e/test_workout_chart.py` — all E2E tests pass
