# Run Holistic Visualization — Design Spec

**Date:** 2026-05-02
**Status:** Approved

## Context

The run detail page currently shows workout structure as a grid of individual segment cards, each with its own HR zone bar and power compliance bar. This makes it hard to compare segments against each other — particularly to see how power targets differ across work intervals, and how compliance tracks across the whole session. The goal is to replace those cards with a single holistic chart that communicates the whole run at a glance, with power compliance as the primary metric.

## What Changes

### Removed
- Individual block detail cards (the grid of per-segment cards)
- Aggregate HR Zone Distribution bar chart (replaced by per-segment HR strips)
- Block Timeline bar (subsumed by proportional segment widths in the new chart)

### Kept
- Run stats header
- Route map
- Prescribed workout card
- AI analysis and chat panel

### Added
A new **Workout Chart** component in the Workout Structure section, replacing everything listed above.

---

## The Chart

Two aligned rows — power and HR — with segment columns proportional to duration.

### Power Row (~130px tall on desktop, ~90px on mobile)

**Y axis:** Watts, consistent scale across all segments. Scale max = `ceil((max(avg_power across all blocks, max target_power.max_w) * 1.15) / 50) * 50`. Minimum scale max of 300W to avoid absurdly tall bands on easy runs.

**Per segment column:**
- Background: dark (`#0d1117`)
- If `target_power` exists:
  - Semi-transparent green dashed band from `min_w` to `max_w` (the target zone)
  - Fill bar from 0 up to `max_w` in green (`rgba(63,185,80,0.55)`)
  - If `avg_power > max_w`: additional orange fill from `max_w` to `avg_power` (`rgba(240,136,62,0.65)`)
  - If `avg_power < min_w`: full fill in red (`rgba(248,81,73,0.55)`) up to `avg_power`
  - Compliance badge text centred at top: e.g. `85% in zone` or `47% above`
- If no `target_power`:
  - Fill bar from 0 to `avg_power` in grey (`rgba(110,118,129,0.35)`)
- Glowing horizontal tick line at `avg_power` height, coloured to match compliance (green / orange / red / grey)
- Avg watts label near the tick line (e.g. `235W`), right-aligned within the column, hidden on very narrow columns (< 40px)

**Y axis ticks:** Shown on the left edge of the leftmost column only. Labels at 4–5 evenly spaced round numbers within the scale. Hidden on mobile if the chart is too cramped.

### HR Zone Row (~20px tall)

A stacked horizontal bar using `Z1_pct` through `Z5_pct` per block. Each zone slice width is proportional to its percentage of the segment.

**Colour palette** (distinct from power's green/orange/red):
- Z1: `#1565c0` — blue
- Z2: `#4527a0` — deep purple
- Z3: `#6a1b9a` — purple
- Z4: `#ad1457` — pink-red
- Z5: `#b71c1c` — dark red

### Segment Labels Row

Segment name below both rows, truncated with ellipsis if too narrow. Colour by `block.type`:
- `warmup`: `#58a6ff` (blue)
- `work`: if target exists — green (`#3fb950`) if `pct_time_in_range ≥ 70`, orange (`#f0883e`) if `pct_time_above > pct_time_below`, else red (`#f85149`); if no target — `#e6edf3` (white)
- `float` / `rest`: `#6e7681` (grey)
- `cooldown`: `#8b949e` (grey)
- `extra`: `#8b949e` (grey)

### Column Widths

Each column width as a percentage = `(segment.duration_min / total_duration_min) * 100%`. Applied as `flex: 0 0 <pct>%` within a flex row. A `min-width: 28px` floor prevents very short segments (e.g. 30s rest) from becoming illegible.

### Separators

A 1px `#21262d` vertical divider between columns.

---

## Responsive Behaviour

| Breakpoint | Power row height | Y-axis ticks | Watts labels | Compliance badge |
|---|---|---|---|---|
| ≥ 600px (desktop) | 130px | shown | shown | shown |
| < 600px (mobile) | 90px | hidden | shown if col ≥ 40px | shown if col ≥ 50px |

On mobile the HR zone strip and segment labels remain unchanged — they are naturally compact. The chart scrolls horizontally only as a last resort; flex proportions should hold at any reasonable phone width since even a 6-segment run distributes well across ~350px.

---

## Data Source

All data is already available in the Jinja template context (`run` dict populated from the YAML/DB in `web.py`). Per block, the template already has access to:

| Field | Used for |
|---|---|
| `block.duration_min` | Column width |
| `block.avg_power` | Bar height, watts label |
| `block.target_power.min_w` / `.max_w` | Target band position |
| `block.target_power.pct_time_in_range` / `_above` / `_below` | Compliance badge, fill colour |
| `block.hr_zones.Z1_pct` … `Z5_pct` | HR zone strip |
| `block.type` | Segment label colour |

The Y-axis scale max is computed in `web.py` inside the `run_detail` view function and passed to the template as `power_scale_max`. This avoids needing complex Jinja arithmetic. Formula: `max(300, ceil(max(all avg_power values + all target max_w values) * 1.15 / 50) * 50)`.

---

## Implementation Notes

- Pure HTML/CSS in `run_detail.html` — no new JS library required
- Chart.js (already included) is **not** used for this chart
- The existing HR Zone Distribution canvas chart and Block Timeline bar are removed
- The segment card grid (`{% for block ... %}`) is replaced by the new chart markup
- A small `<style>` block scoped to this component handles the chart CSS, or styles are added to the existing `<style>` tag in the template
- Y-axis scale max computed in a Jinja `{% set %}` block at the top of the chart section

---

## Hover Tooltips

Each segment column shows a tooltip on hover containing the fuller per-segment metrics not visible in the chart itself.

**Trigger:** `mouseenter` / `mouseleave` on the segment column (both the power bar and the HR strip). On touch devices the tooltip appears on tap and dismisses on tap-away.

**Tooltip content:**
- Segment name + type badge
- Duration and distance
- Avg power (W) + compliance summary if target exists (e.g. "85% in zone · 9% above · 6% below")
- Target zone if present (e.g. "Target: 220–250 W")
- Avg HR (bpm)
- HR zone breakdown (Z1–Z5 %)
- Running dynamics (shown only if present in the block data):
  - Cadence (steps/min)
  - Ground contact time (ms)
  - Vertical oscillation (cm)
  - Step length (m)
  - Form power (W) and form power ratio (%)
  - Leg spring stiffness

**Positioning:** Tooltip floats above the hovered column, centred on it, flipping to below if it would overflow the top of the viewport. On mobile, the tooltip is fixed to the bottom of the screen to avoid clipping.

**Implementation:** A single shared tooltip `<div>` positioned with JS (`mousemove`/`mouseenter` on each column populates and repositions it). Tooltip content rendered from `data-*` attributes on each column element, populated by Jinja at render time. Pure JS — no library required.

---

## Out of Scope

- Collapsible/expandable segment detail — can be added later once the chart proves its value

---

## Verification

1. Load a run with multiple work segments that have power targets — confirm target bands render at correct relative heights, compliance colours are correct, avg watts line is visible
2. Load a run with no power targets on any segment — confirm all bars render in grey with watts labels, no target bands shown
3. Load a run with a mix of targeted and untargeted segments — correct rendering for both within the same chart
4. Resize browser to ~375px width — confirm chart remains readable, no overflow, labels truncate gracefully
5. Hover each segment — confirm tooltip appears with correct data, running dynamics shown where available and absent where not
6. On mobile (~375px): tap a segment, confirm tooltip appears at bottom of screen and dismisses on tap-away
7. Confirm the old segment cards, HR zone chart, and block timeline bar are no longer present
8. Run existing web tests (`pytest tests/test_web.py`) — no regressions
