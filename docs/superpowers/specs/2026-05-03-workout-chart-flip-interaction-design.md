# Workout Chart — Flip Interaction Design

**Date:** 2026-05-03  
**Status:** Approved

## Problem

The existing workout chart uses a hover tooltip to show per-segment stats. On touch screens this tooltip renders below the chart and is poorly positioned on small viewports. The interaction model is mouse-first and unsuitable for the primary use case: viewing run details on a phone.

## Solution

Replace the tooltip with a tap-to-flip interaction. The workout chart overview remains the default view. Tapping a segment flips the card and expands it to show a stats detail view. Tapping the detail view flips back. Swiping left/right on the detail view navigates between segments.

## Interaction Model

### Overview (default state)
- Renders exactly as the current chart: power bars, compliance strip, HR zone strip, segment name labels
- Legends are removed (they add visual noise on small screens)
- Every segment column is tappable

### Tap to open detail
- Tapping a column triggers a 3D card flip (rotateY 0→180, scale 0.92→1, opacity 0→1)
- During the flip animation the detail card is `position: absolute` overlaying the frozen stage
- After the animation (~400ms) the overview gets `display: none`, the detail card switches to `position: relative` in normal flow, and the containing card expands to the detail's natural height
- On open, the page scrolls so the top of the card is at the top of the viewport

### Detail view
- Header: segment name + type badge (warmup / work / rest / cooldown) + "tap to close ✕" hint
- 3×3 stats grid (in order): Duration, Distance, Avg Pace (computed from duration/distance), Avg Power, Target Range, Avg HR, Cadence, Step Length, GCT
- Full-width compliance strip (blue/green/red: % below / in / above target; "no target" label when absent)
- Full-width HR zone strip (Z1–Z5 colours)
- Dot navigation row (one dot per segment, active dot highlighted in orange; swipe hint text)

### Tap to close
- Tapping anywhere on the detail card closes it
- Reverse animation: detail switches back to `position: absolute`, overview becomes visible, flip animates out (rotateY 0→-180)
- After animation detail is hidden, overview resumes

### Swipe to navigate
- Horizontal swipe (or mouse drag on desktop) on the detail card moves to the next (swipe left) or previous (swipe right) segment without returning to the overview
- Transition: opacity fades out/in (140ms) while content is re-rendered
- Dot navigation updates to reflect the current segment
- Wraps around (last → first, first → last)
- Swipe detection: horizontal movement > 8px triggers swipe mode and suppresses vertical scroll; threshold to commit is 40px

## Stats grid fields

| Cell | Source field | Format |
|------|-------------|--------|
| Duration | `block.duration_min` | `X min` |
| Distance | `block.distance_km` | `X.XX km` |
| Avg Pace | computed: `duration_min / distance_km` | `M:SS/km` |
| Avg Power | `block.avg_power` | `X W` |
| Target Range | `block.target_power.min_w`–`max_w` | `X–Y W` (or `—`) |
| Avg HR | `block.avg_hr` | `X bpm` |
| Cadence | `block.running_dynamics.cadence_med` | `X spm` (or `—`) |
| Step Length | `block.running_dynamics.step_length_med` | `X.XX m` (or `—`) |
| GCT | `block.running_dynamics.gct_med` | `X ms` (or `—`) |

Missing values render as `—` in muted grey.

## Visual design

- Light theme throughout (matches production)
- Detail card background: `#fff`, border: `1px solid #e2e8f0`, box-shadow for depth
- Stat boxes: `#f8fafc` background, `1px solid #e2e8f0` border, `border-radius: 8px`
- "In zone" value coloured green (`#16a34a`), above red (`#e11d48`), below blue (`#2563eb`)
- Strip heights match overview: compliance 20px, HR zones 22px, both with `border-radius: 10px` and `1px solid #cbd5e1` border
- Dot nav: 7px circles, inactive `#e2e8f0`, active `#ea580c` (brand orange), scale(1.3) on active
- Flip animation: `cubic-bezier(0.4,0,0.2,1)`, 400ms

## Implementation scope

- Changes are confined to `runcoach/web/templates/run_detail.html`
- The Jinja template renders `data-segment` JSON per column as before; JS reads this on tap
- The tooltip (`#wc-tooltip`) and all its JS are removed
- Legends (`div.wc-legend`) are removed
- The `.wc-col` cursor changes from `default` to `pointer`
- No Python / backend changes required

## Scroll-to-top on open

`window.scrollTo({ top: cardTop - 8, behavior: 'smooth' })` where `cardTop` is `card.getBoundingClientRect().top + window.scrollY`. Fires after the flip animation starts (not after it completes, so the scroll happens concurrently with the flip).

## Out of scope

- Avg pace as a stored field in the parser (computed at render time only)
- Any change to the overview chart visual design
- Changes to the mobile bottom-sheet fallback (removed in favour of this approach)
