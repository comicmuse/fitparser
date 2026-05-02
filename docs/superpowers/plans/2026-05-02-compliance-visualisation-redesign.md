# Compliance Visualisation Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the colour-fill-based compliance display in the workout chart with a neutral power bar + coloured avg line + dedicated compliance strip, so that power position and time distribution are visually distinct.

**Architecture:** All changes are confined to `runcoach/web/templates/run_detail.html`. The CSS block, Jinja template logic, and legend are updated in place — no Python, no new files, no backend changes. Unit tests in `tests/test_web.py::TestWorkoutChart` are updated to match the new class names.

**Tech Stack:** Jinja2 templating, inline CSS (including CSS container queries), vanilla JS (no changes needed)

---

## File Map

| File | Change |
|---|---|
| `runcoach/web/templates/run_detail.html` | CSS: replace fill classes, add compliance strip + container query, update HR strip, update legend; Jinja: remove badge, add compliance strip block, update segment name colouring, update grid/col styles |
| `tests/test_web.py` | Update `TestWorkoutChart` assertions to match new class names |

---

### Task 1: Update unit tests to reflect new class names (write failing tests first)

**Files:**
- Modify: `tests/test_web.py:1289-1331`

The spec changes two CSS classes that the tests assert on:
- `wc-fill--none` → removed; `cs-none` added (no-target compliance strip placeholder)
- `wc-fill--in` → removed; `cs-in` added (in-range compliance block)

- [ ] **Step 1: Update `test_workout_chart_renders_with_targets`**

In `tests/test_web.py`, locate `test_workout_chart_renders_with_targets` (around line 1254). Replace the assertion block at the bottom (lines ~1289–1304) with:

```python
        # New chart structure present
        assert "wc-grid" in html
        assert "wc-col" in html
        assert "wc-power" in html
        assert "wc-hr" in html
        assert "data-segment" in html
        assert "wc-tooltip" in html

        # Compliance strip present for run with targets
        assert "comp-strip" in html
        assert "cs-in" in html

        # Coloured fills are gone — fill is always neutral
        assert "wc-fill--in" not in html
        assert "wc-fill--above" not in html
        assert "wc-fill--below" not in html

        # Segment names appear
        assert "warmup" in html
        assert "active_1" in html

        # Old elements are gone
        assert "hrZoneChart" not in html
        assert "block-grid" not in html
        assert "Block Timeline" not in html
```

- [ ] **Step 2: Update `test_workout_chart_no_targets_renders`**

In the same file, replace the assertion block at the bottom of `test_workout_chart_no_targets_renders` (around lines 1328–1331) with:

```python
        assert "wc-grid" in html
        assert "comp-strip" in html
        assert "cs-none" in html

        # Old coloured fill class must be gone
        assert "wc-fill--none" not in html

        assert "easy" in html
```

- [ ] **Step 3: Run tests to confirm they fail (expected)**

```bash
cd /home/colm/git/fitparser && source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```

Expected: both tests FAIL (the old classes are still in the template).

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/test_web.py
git commit -m "test: update WorkoutChart assertions for compliance redesign (red)"
```

---

### Task 2: Update CSS — replace old classes, add new ones

**Files:**
- Modify: `runcoach/web/templates/run_detail.html:145-222` (the `<style>` block)

Work through the CSS block section by section.

- [ ] **Step 1: Update `.wc-grid` and `.wc-col`**

Current:
```css
.wc-grid { display: flex; width: 100%; gap: 4px; }
.wc-col { display: flex; flex-direction: column; gap: 3px; min-width: 28px; cursor: default; border-right: 1px solid #21262d; }
```

Replace with:
```css
.wc-grid { display: flex; width: 100%; gap: 6px; overflow: hidden; }
.wc-col { display: flex; flex-direction: column; gap: 3px; min-width: 0; cursor: default; }
```

Note: `min-width: 28px` floor is enforced by the Jinja `flex-basis` value — columns are never rendered narrower than 28px because `col_pct` is computed from `duration_min / total_dur * 100`, and very short segments still get at least their proportional width. The `min-width: 0` here prevents the flex item from overflowing when the label is wider than the column.

- [ ] **Step 2: Update `.wc-fill` classes — remove old, add neutral**

Remove these CSS rules entirely:
```css
.wc-fill { position: absolute; bottom: 0; left: 0; right: 0; border-radius: 3px 3px 0 0; }
.wc-fill--in    { background: rgba(63,185,80,0.55); }
.wc-fill--above { background: rgba(240,136,62,0.65); }
.wc-fill--below { background: rgba(248,81,73,0.55); }
.wc-fill--none  { background: rgba(110,118,129,0.35); }
```

Replace with a single neutral fill class:
```css
.wc-fill { position: absolute; bottom: 0; left: 0; right: 0; border-radius: 3px 3px 0 0; background: rgba(255,255,255,0.04); }
```

- [ ] **Step 3: Update `.wc-target-band` — stronger contrast**

Current:
```css
.wc-target-band {
  position: absolute; left: 0; right: 0; pointer-events: none;
  background: rgba(63,185,80,0.1);
  border-top: 1px dashed rgba(63,185,80,0.5);
  border-bottom: 1px dashed rgba(63,185,80,0.5);
}
```

Replace with:
```css
.wc-target-band {
  position: absolute; left: 0; right: 0; pointer-events: none;
  background: rgba(255,255,255,0.11);
  border-top: 1px solid rgba(255,255,255,0.38);
  border-bottom: 1px solid rgba(255,255,255,0.38);
}
```

- [ ] **Step 4: Update `.wc-avg-line` colours and glow**

Current:
```css
.wc-avg-line { position: absolute; left: 0; right: 0; height: 2px; border-radius: 1px; pointer-events: none; z-index: 3; }
.wc-avg-line--in    { background: #3fb950; box-shadow: 0 0 4px rgba(63,185,80,0.6); }
.wc-avg-line--above { background: #f0883e; box-shadow: 0 0 4px rgba(240,136,62,0.6); }
.wc-avg-line--below { background: #f85149; box-shadow: 0 0 4px rgba(248,81,73,0.6); }
.wc-avg-line--none  { background: #8b949e; }
```

Replace with (new colours and stronger glow per spec):
```css
.wc-avg-line { position: absolute; left: 0; right: 0; height: 2px; border-radius: 1px; pointer-events: none; z-index: 3; }
.wc-avg-line--in    { background: #00e676; box-shadow: 0 0 7px 1px rgba(0,230,118,0.75), 0 0 14px rgba(0,230,118,0.4); }
.wc-avg-line--above { background: #ff3d71; box-shadow: 0 0 7px 1px rgba(255,61,113,0.75), 0 0 14px rgba(255,61,113,0.4); }
.wc-avg-line--below { background: #2979ff; box-shadow: 0 0 7px 1px rgba(41,121,255,0.75), 0 0 14px rgba(41,121,255,0.4); }
.wc-avg-line--none  { background: #6e7681; }
```

- [ ] **Step 5: Remove `.wc-badge` CSS rule**

The badge is being removed. Delete:
```css
.wc-badge {
  position: absolute; top: 4px; left: 0; right: 0; text-align: center;
  font-size: 0.58rem; font-weight: 700;
  color: rgba(255,255,255,0.85); text-shadow: 0 1px 3px rgba(0,0,0,0.8);
  pointer-events: none; z-index: 4; line-height: 1.3;
}
```

- [ ] **Step 6: Add compliance strip CSS**

After the `.wc-avg-line` rules, add:
```css
.comp-strip {
  width: 100%; height: 20px; display: flex;
  border-radius: 10px; overflow: hidden; border: 1px solid #30363d;
}
.cs-below { background: rgba(41,121,255,0.7); }
.cs-in    { background: rgba(0,230,118,0.6); }
.cs-above { background: rgba(255,61,113,0.7); }
.cs-none  {
  flex: 1; background: #1c2128;
  display: flex; align-items: center; justify-content: center;
  color: #444d56; font-size: 0.6rem;
}
```

- [ ] **Step 7: Update `.wc-hr` — increase height, add border-radius pill**

Current:
```css
.wc-hr {
  width: 100%; height: 20px; display: flex;
  border-radius: 4px; overflow: hidden; border: 1px solid #30363d;
}
```

Replace with:
```css
.wc-hr {
  width: 100%; height: 22px; display: flex;
  border-radius: 10px; overflow: hidden; border: 1px solid #30363d;
}
```

- [ ] **Step 8: Add container query for HR zone labels**

After `.wc-hz5`, add:
```css
.wc-hz { height: 100%; flex-shrink: 0; container-type: inline-size; display: flex; align-items: center; justify-content: center; }
.wc-hz span { display: none; font-size: 0.5rem; font-weight: 700; color: rgba(255,255,255,0.8); text-shadow: 0 1px 2px rgba(0,0,0,0.6); line-height: 1; }
@container (min-width: 20px) {
  .wc-hz span { display: block; }
}
```

Note: the existing `.wc-hz { height: 100%; flex-shrink: 0; }` rule (line 189) needs to be replaced — do not duplicate it. The new rule above replaces that line entirely.

- [ ] **Step 9: Commit CSS changes**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "style: update workout chart CSS for compliance redesign"
```

---

### Task 3: Update Jinja template — power bar, compliance strip, segment names, legend

**Files:**
- Modify: `runcoach/web/templates/run_detail.html:225-342`

- [ ] **Step 1: Update `.wc-col` flex style in Jinja**

Current (line 274):
```html
<div class="wc-col" style="flex:0 0 {{ col_pct }}%;"
```

Replace with (allow shrink, add `min-width: 0`):
```html
<div class="wc-col" style="flex:1 0 {{ col_pct }}%; min-width: 0;"
```

- [ ] **Step 2: Remove type-based `name_color` logic and badge Jinja**

Locate the block starting at line 254:
```jinja
{% if block.type == 'warmup' %}{% set name_color = '#58a6ff' %}
{% elif block.type == 'work' %}
  {% if has_tgt %}
    {% if pct_in >= 70 %}{% set name_color = '#3fb950' %}
    {% elif pct_above > pct_below %}{% set name_color = '#f0883e' %}
    {% else %}{% set name_color = '#f85149' %}{% endif %}
  {% else %}{% set name_color = '#e6edf3' %}{% endif %}
{% elif block.type in ['float', 'rest'] %}{% set name_color = '#6e7681' %}
{% else %}{% set name_color = '#8b949e' %}{% endif %}
```

Replace this entire block with a single line:
```jinja
{% set name_color = '#8b949e' %}
```

- [ ] **Step 3: Replace coloured fills with single neutral fill in the power bar**

Inside `<!-- Power bar -->`, locate the conditional fill block (lines ~287–296):
```jinja
{% if compliance == 'above' %}
  <div class="wc-fill wc-fill--above" style="height:{{ avg_pct }}%;"></div>
  <div class="wc-fill wc-fill--in"    style="height:{{ top_pct }}%;"></div>
{% elif compliance == 'in' %}
  <div class="wc-fill wc-fill--in"    style="height:{{ avg_pct }}%;"></div>
{% elif compliance == 'below' %}
  <div class="wc-fill wc-fill--below" style="height:{{ avg_pct }}%;"></div>
{% else %}
  <div class="wc-fill wc-fill--none"  style="height:{{ avg_pct }}%;"></div>
{% endif %}
```

Replace with a single neutral fill (always rendered, always same class):
```jinja
{% if avg_p > 0 %}
  <div class="wc-fill" style="height:{{ avg_pct }}%;"></div>
{% endif %}
```

- [ ] **Step 4: Remove the compliance badge from the power bar**

Delete the entire badge block (lines ~301–307):
```jinja
{% if has_tgt %}
  <span class="wc-badge">
    {% if compliance == 'above' %}{{ pct_above }}% above
    {% elif compliance == 'below' %}{{ pct_below }}% below
    {% else %}{{ pct_in }}% in zone{% endif %}
  </span>
{% endif %}
```

The closing `</div>` for `.wc-power` remains.

- [ ] **Step 5: Add compliance strip between power bar and HR strip**

After the closing `</div>` of `.wc-power` (and before `<!-- HR zone strip -->`), insert:

```jinja
        <!-- Compliance strip -->
        <div class="comp-strip">
          {% if has_tgt %}
            {% if pct_below > 0 %}<div class="cs-below" style="width:{{ pct_below }}%;"></div>{% endif %}
            {% if pct_in > 0 %}<div class="cs-in" style="width:{{ pct_in }}%;"></div>{% endif %}
            {% if pct_above > 0 %}<div class="cs-above" style="width:{{ pct_above }}%;"></div>{% endif %}
          {% else %}
            <div class="cs-none">no target</div>
          {% endif %}
        </div>
```

- [ ] **Step 6: Add Z-labels inside HR zone slices**

In the `<!-- HR zone strip -->` block, update each `wc-hz` div to include the label span:

Current:
```jinja
<div class="wc-hz wc-hz1" style="width:{{ block.hr_zones.Z1_pct | default(0) | round(1) }}%;"></div>
<div class="wc-hz wc-hz2" style="width:{{ block.hr_zones.Z2_pct | default(0) | round(1) }}%;"></div>
<div class="wc-hz wc-hz3" style="width:{{ block.hr_zones.Z3_pct | default(0) | round(1) }}%;"></div>
<div class="wc-hz wc-hz4" style="width:{{ block.hr_zones.Z4_pct | default(0) | round(1) }}%;"></div>
<div class="wc-hz wc-hz5" style="width:{{ block.hr_zones.Z5_pct | default(0) | round(1) }}%;"></div>
```

Replace with:
```jinja
<div class="wc-hz wc-hz1" style="width:{{ block.hr_zones.Z1_pct | default(0) | round(1) }}%;"><span>Z1</span></div>
<div class="wc-hz wc-hz2" style="width:{{ block.hr_zones.Z2_pct | default(0) | round(1) }}%;"><span>Z2</span></div>
<div class="wc-hz wc-hz3" style="width:{{ block.hr_zones.Z3_pct | default(0) | round(1) }}%;"><span>Z3</span></div>
<div class="wc-hz wc-hz4" style="width:{{ block.hr_zones.Z4_pct | default(0) | round(1) }}%;"><span>Z4</span></div>
<div class="wc-hz wc-hz5" style="width:{{ block.hr_zones.Z5_pct | default(0) | round(1) }}%;"><span>Z5</span></div>
```

- [ ] **Step 7: Update the legend**

Current legend block (lines ~328–341):
```html
<div class="wc-legend">
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(63,185,80,0.55);"></span>In target</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(240,136,62,0.65);"></span>Above</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(248,81,73,0.55);"></span>Below</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(110,118,129,0.35);border:1px solid #6e7681;"></span>No target</span>
  <span class="wc-leg-item">
    <span class="wc-leg-hr">
      <span style="background:#1565c0;"></span><span style="background:#4527a0;"></span>
      <span style="background:#6a1b9a;"></span><span style="background:#ad1457;"></span>
      <span style="background:#b71c1c;"></span>
    </span>
    HR Z1&rarr;Z5
  </span>
</div>
```

Replace with:
```html
<div class="wc-legend">
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(255,255,255,0.11);border:1px solid rgba(255,255,255,0.38);"></span>Target range</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:#00e676;box-shadow:0 0 5px rgba(0,230,118,0.7);"></span>Avg — in target</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:#ff3d71;box-shadow:0 0 5px rgba(255,61,113,0.7);"></span>Avg — too high</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:#2979ff;box-shadow:0 0 5px rgba(41,121,255,0.7);"></span>Avg — too low</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(0,230,118,0.6);"></span>% time in zone</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(255,61,113,0.7);"></span>% time above</span>
  <span class="wc-leg-item"><span class="wc-leg-swatch" style="background:rgba(41,121,255,0.7);"></span>% time below</span>
  <span class="wc-leg-item">
    <span class="wc-leg-hr">
      <span style="background:#1565c0;"></span><span style="background:#4527a0;"></span>
      <span style="background:#6a1b9a;"></span><span style="background:#ad1457;"></span>
      <span style="background:#b71c1c;"></span>
    </span>
    HR Z1&rarr;Z5
  </span>
</div>
```

- [ ] **Step 8: Commit Jinja/template changes**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: compliance redesign — strip, neutral fill, updated avg line, z-labels, legend"
```

---

### Task 4: Run tests and verify

- [ ] **Step 1: Run unit tests**

```bash
cd /home/colm/git/fitparser && source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```

Expected output:
```
tests/test_web.py::TestWorkoutChart::test_workout_chart_renders_with_targets PASSED
tests/test_web.py::TestWorkoutChart::test_workout_chart_no_targets_renders PASSED
```

- [ ] **Step 2: Run full unit test suite to check for regressions**

```bash
pytest -q --no-cov
```

Expected: all tests pass, 0 failures.

- [ ] **Step 3: Run E2E tests**

```bash
pytest -m e2e --no-cov -v tests/e2e/test_workout_chart.py
```

Expected: all existing E2E tests pass (no structural class names changed that the E2E tests use — they check `wc-col`, `wc-power`, `wc-hr`, `data-segment`, `wc-tooltip` which are all still present).

- [ ] **Step 4: Manual verification checklist**

Start the dev server:
```bash
python -m runcoach.web
```

Open a run with power targets:
1. Confirm avg line is **green with glow** when avg is in range — no coloured fill behind it
2. Confirm **compliance strip** (pill shape) appears between power bar and HR strip, showing green/blue/red proportional blocks
3. Confirm target band is **visibly brighter** (solid white borders, not dashed green)
4. On a segment above range: confirm avg line is red/pink; compliance strip shows red on right
5. On a segment below range: confirm avg line is blue; compliance strip shows blue on left
6. Open a run with **no power targets**: compliance strip shows "no target" placeholder text, avg line is grey
7. Hover a segment — tooltip content unchanged
8. Confirm HR labels (`Z1`–`Z5`) appear inside wide-enough zone slices, absent in narrow slices
9. Resize browser to ~375px — no overflow, pill strips still visible

- [ ] **Step 5: Final commit if any fixups were needed**

```bash
git add -p  # stage only actual changes
git commit -m "fix: post-verification cleanup for compliance redesign"
```

(Skip this step if no fixups are needed.)
