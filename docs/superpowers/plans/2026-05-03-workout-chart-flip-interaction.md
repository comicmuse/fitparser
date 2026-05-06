# Workout Chart Flip Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hover tooltip on the run detail workout chart with a touch-first tap-to-flip interaction that shows per-segment stats on a detail card, with swipe navigation between segments.

**Architecture:** All changes are confined to `runcoach/web/templates/run_detail.html`. The Jinja template already renders `data-segment` JSON on each `.wc-col` element — the JS reads this on tap. The tooltip div and its JS are removed; a new detail card div and new JS replace them. The overview chart HTML is unchanged.

**Tech Stack:** Vanilla JS, CSS3 transforms, Jinja2 template. No new dependencies.

---

### Task 1: Update tests to reflect removed tooltip and added flip card

**Files:**
- Modify: `tests/test_web.py:1295` (line `assert "wc-tooltip" in html`)

The test `test_workout_chart_renders_with_targets` currently asserts `wc-tooltip` is present. After this change the tooltip is gone and the flip card is present. Update the assertion before touching the template so the test fails red first.

- [ ] **Step 1: Run the existing tests to confirm they pass now**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```
Expected: all pass (green baseline).

- [ ] **Step 2: Update the test assertions**

In `tests/test_web.py`, find `test_workout_chart_renders_with_targets` (around line 1254). Replace:

```python
        assert "wc-tooltip" in html
```

with:

```python
        assert "wc-detail" in html
        assert "wc-tooltip" not in html
        assert "wc-legend" not in html
```

- [ ] **Step 3: Run the tests to confirm they now fail**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart::test_workout_chart_renders_with_targets -v
```
Expected: FAIL — `wc-detail` not in html, `wc-tooltip` still in html.

- [ ] **Step 4: Commit the failing test**

```bash
git add tests/test_web.py
git commit -m "test: update WorkoutChart assertions for flip interaction (red)"
```

---

### Task 2: Remove tooltip HTML, tooltip CSS, and legend from the template

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

- [ ] **Step 1: Remove the tooltip CSS block**

In `run_detail.html`, delete the entire `/* Tooltip */` CSS block and its mobile override (lines ~207–228). This is the block starting with `/* Tooltip */` and ending with the closing `}` of the `@media (max-width: 599px)` rule. Also delete the tooltip-related class definitions: `.wc-tt-title`, `.wc-tt-section`, `.wc-tt-row`. Also delete the legend CSS: `.wc-legend`, `.wc-leg-item`, `.wc-leg-swatch`, `.wc-leg-hr`.

The CSS to remove spans from `/* Tooltip */` down to and including the `@media` block closing brace:

```css
/* DELETE from here: */
.wc-legend { display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 14px; font-size: 0.7rem; color: var(--fg-muted); }
.wc-leg-item { display: flex; align-items: center; gap: 5px; }
.wc-leg-swatch { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.wc-leg-hr { display: flex; gap: 2px; }
.wc-leg-hr span { display: inline-block; width: 8px; height: 10px; border-radius: 1px; }
/* Tooltip */
#wc-tooltip {
  display: none; position: fixed; z-index: 1000;
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 10px 14px; min-width: 180px; max-width: 260px;
  font-size: 0.78rem; color: #1c1917; pointer-events: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}
#wc-tooltip.wc-tooltip--visible { display: block; }
.wc-tt-title { font-weight: 700; font-size: 0.85rem; margin-bottom: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 5px; }
.wc-tt-section { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; margin: 8px 0 4px; }
.wc-tt-row { display: flex; justify-content: space-between; gap: 12px; padding: 1px 0; color: #64748b; }
.wc-tt-row span:last-child { color: #1c1917; font-weight: 600; }
@media (max-width: 599px) {
  .wc-power { height: 90px; }
  .wc-tick { display: none; }
  #wc-tooltip {
    position: fixed; bottom: 0; left: 0; right: 0; top: auto;
    max-width: 100%; border-radius: 12px 12px 0 0;
    padding: 16px; pointer-events: auto;
  }
}
/* DELETE to here */
```

Keep the `@media` wrapper but only the two rules that are still needed (`wc-power` height and `wc-tick` display):

```css
@media (max-width: 599px) {
  .wc-power { height: 90px; }
  .wc-tick { display: none; }
}
```

- [ ] **Step 2: Change `.wc-col` cursor from `default` to `pointer`**

Find:
```css
.wc-col { display: flex; flex-direction: column; gap: 3px; min-width: 0; cursor: default; }
```

Replace with:
```css
.wc-col { display: flex; flex-direction: column; gap: 3px; min-width: 0; cursor: pointer; -webkit-tap-highlight-color: transparent; touch-action: pan-y; }
```

- [ ] **Step 3: Remove the legend HTML block**

Find and delete the entire `<div class="wc-legend">` block (lines ~321–337 in the original file, inside `<div class="workout-chart">`). It starts with `<div class="wc-legend">` and ends with `</div>`.

- [ ] **Step 4: Remove the tooltip div and its entire `<script>` block**

Find and delete:
```html
<div id="wc-tooltip" role="tooltip"></div>

<script>
(function () {
  ...all tooltip JS...
})();
</script>
```

This is everything from `<div id="wc-tooltip"` through the closing `</script>` tag of the tooltip IIFE.

- [ ] **Step 5: Run the tests**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```
Expected: `test_workout_chart_renders_with_targets` still fails (wc-detail not in html). Other chart tests should still pass.

- [ ] **Step 6: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "refactor: remove tooltip and legend from workout chart"
```

---

### Task 3: Add flip-card CSS to the template

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

Add the following CSS inside the existing `<style>` block (before the closing `</style>` tag):

- [ ] **Step 1: Add the flip stage and detail card CSS**

```css
/* Flip interaction */
.flip-stage { perspective: 1200px; position: relative; }
.overview { transition: opacity 0.2s, transform 0.25s; transform-origin: center center; }
.overview.wc-hiding { opacity: 0; transform: scale(0.97); pointer-events: none; }
.overview.wc-gone   { display: none; }

.wc-detail {
  display: none;
  background: #fff; border-radius: 10px; border: 1px solid #e2e8f0;
  padding: 16px; flex-direction: column; gap: 0;
  transform-origin: center center;
  transform: rotateY(180deg) scale(0.92); opacity: 0;
  transition: transform 0.4s cubic-bezier(0.4,0,0.2,1), opacity 0.3s;
  backface-visibility: hidden; touch-action: pan-y;
  -webkit-tap-highlight-color: transparent; cursor: pointer;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
}
.wc-detail.wc-phase-fly {
  position: absolute; inset: 0; display: flex;
}
.wc-detail.wc-phase-open {
  position: relative; display: flex;
  transform: rotateY(0deg) scale(1); opacity: 1;
}

.wc-detail-header {
  display: flex; align-items: baseline; gap: 8px;
  padding-bottom: 10px; border-bottom: 1px solid #e2e8f0; margin-bottom: 12px; flex-shrink: 0;
}
.wc-detail-name { font-size: 0.95rem; font-weight: 700; color: #1c1917; }
.wc-detail-type {
  font-size: 0.62rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em;
  background: #f1f5f9; border-radius: 999px; padding: 1px 7px;
}
.wc-detail-hint { margin-left: auto; font-size: 0.6rem; color: #94a3b8; }

.wc-detail-stats { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 7px; flex-shrink: 0; }
.wc-stat-box {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 9px 6px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center;
}
.wc-stat-val { font-size: 0.92rem; font-weight: 700; color: #1c1917; line-height: 1.1; }
.wc-stat-lbl { font-size: 0.5rem; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; margin-top: 3px; }
.wc-stat-val--in    { color: #16a34a; }
.wc-stat-val--above { color: #e11d48; }
.wc-stat-val--below { color: #2563eb; }
.wc-stat-val--muted { color: #94a3b8; }

.wc-detail-strips { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; flex-shrink: 0; }
.wc-detail-strip { width: 100%; height: 20px; display: flex; border-radius: 10px; overflow: hidden; border: 1px solid #cbd5e1; }
.wc-detail-strip--hr { height: 22px; }

.wc-detail-footer {
  display: flex; align-items: center; justify-content: center; gap: 7px; margin-top: 10px; flex-shrink: 0;
}
.wc-seg-dot { width: 7px; height: 7px; border-radius: 50%; background: #e2e8f0; transition: background 0.2s, transform 0.2s; cursor: pointer; flex-shrink: 0; }
.wc-seg-dot--active { background: #ea580c; transform: scale(1.3); }
.wc-swipe-hint { font-size: 0.6rem; color: #cbd5e1; margin-left: 8px; }
```

- [ ] **Step 2: Run the tests**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```
Expected: same result as after Task 2 (css-only change, no new test assertions satisfied yet).

- [ ] **Step 3: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: add flip card CSS to workout chart"
```

---

### Task 4: Add the detail card HTML to the template

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

- [ ] **Step 1: Wrap the existing chart content in `.flip-stage` and `.overview`**

Find the `<div class="workout-chart">` block. Wrap the inner content (scale-label + wc-grid) in two new divs:

Before (inside `<div class="workout-chart">`):
```html
    <div class="wc-scale-label">Power — 0 to {{ power_scale_max }} W</div>
    <div class="wc-grid">
      ...
    </div>
```

After:
```html
    <div class="flip-stage" id="wc-stage">
      <div class="overview" id="wc-overview">
        <div class="wc-scale-label">Power — 0 to {{ power_scale_max }} W</div>
        <div class="wc-grid">
          ...
        </div>
      </div>

      <div class="wc-detail" id="wc-detail">
        <div class="wc-detail-header">
          <span class="wc-detail-name" id="wc-d-name"></span>
          <span class="wc-detail-type" id="wc-d-type"></span>
          <span class="wc-detail-hint">tap to close ✕</span>
        </div>
        <div class="wc-detail-stats" id="wc-d-stats"></div>
        <div class="wc-detail-strips" id="wc-d-strips"></div>
        <div class="wc-detail-footer" id="wc-d-footer"></div>
      </div>
    </div>
```

- [ ] **Step 2: Run the tests**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```
Expected: `test_workout_chart_renders_with_targets` now passes (`wc-detail` is in html). All other chart tests pass too.

- [ ] **Step 3: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: add flip detail card HTML to workout chart"
```

---

### Task 5: Add the flip interaction JavaScript

**Files:**
- Modify: `runcoach/web/templates/run_detail.html`

Add a new `<script>` block immediately after the closing `</div>` of the `<div class="card">` that wraps the workout chart (i.e. after the entire workout chart card closes). This script must be inside the `{% if workout_data and workout_data.blocks %}` Jinja block so it only renders when the chart exists.

- [ ] **Step 1: Add the script block**

```html
<script>
(function () {
  var stage     = document.getElementById('wc-stage');
  var overview  = document.getElementById('wc-overview');
  var detail    = document.getElementById('wc-detail');
  var card      = detail && detail.closest('.card');
  if (!stage || !overview || !detail) return;

  var currentSeg = -1;
  var animating  = false;

  // Collect segment data from DOM
  var cols = Array.prototype.slice.call(overview.querySelectorAll('.wc-col'));
  var segments = cols.map(function (col) {
    return JSON.parse(col.getAttribute('data-segment'));
  });

  // Wire up tap on each column
  cols.forEach(function (col, i) {
    col.addEventListener('click', function (e) {
      e.stopPropagation();
      openDetail(i);
    });
  });

  // Tap on detail card closes it
  detail.addEventListener('click', function (e) {
    closeDetail();
  });

  function openDetail(idx) {
    if (animating) return;
    animating = true;
    currentSeg = idx;
    renderDetail(idx);

    // Freeze stage height at overview height for the fly-in
    stage.style.height = overview.offsetHeight + 'px';
    overview.classList.add('wc-hiding');

    // Place detail as absolute overlay, start from rotated state
    detail.classList.add('wc-phase-fly');
    detail.getBoundingClientRect(); // force reflow

    // Scroll card top to viewport
    if (card) {
      var cardTop = card.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: cardTop - 8, behavior: 'smooth' });
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        detail.style.transform = 'rotateY(0deg) scale(1)';
        detail.style.opacity = '1';

        setTimeout(function () {
          overview.classList.add('wc-gone');
          detail.classList.remove('wc-phase-fly');
          detail.classList.add('wc-phase-open');
          stage.style.height = '';
          animating = false;
        }, 410);
      });
    });
  }

  function closeDetail() {
    if (animating || !detail.classList.contains('wc-phase-open')) return;
    animating = true;

    // Freeze stage at current detail height, switch back to absolute
    stage.style.height = detail.offsetHeight + 'px';
    detail.classList.remove('wc-phase-open');
    detail.classList.add('wc-phase-fly');
    overview.classList.remove('wc-gone');
    detail.getBoundingClientRect(); // force reflow

    detail.style.transform = 'rotateY(-180deg) scale(0.92)';
    detail.style.opacity = '0';
    overview.classList.remove('wc-hiding');

    setTimeout(function () {
      detail.classList.remove('wc-phase-fly');
      detail.style.transform = '';
      detail.style.opacity = '';
      stage.style.height = '';
      currentSeg = -1;
      animating = false;
    }, 410);
  }

  function goToSeg(idx) {
    idx = ((idx % segments.length) + segments.length) % segments.length;
    currentSeg = idx;
    detail.style.opacity = '0';
    setTimeout(function () {
      renderDetail(idx);
      detail.style.opacity = '1';
    }, 140);
  }

  function fmtPace(duration_min, distance_km) {
    if (duration_min == null || distance_km == null || distance_km === 0) return '—';
    var raw = duration_min / distance_km;
    var m = Math.floor(raw);
    var s = Math.round((raw - m) * 60);
    if (s === 60) { m++; s = 0; }
    return m + ':' + (s < 10 ? '0' : '') + s + '/km';
  }

  function mkStatBox(val, lbl, mod) {
    var box = document.createElement('div');
    box.className = 'wc-stat-box';
    var v = document.createElement('div');
    v.className = 'wc-stat-val' + (mod ? ' wc-stat-val--' + mod : '');
    v.textContent = val;
    var l = document.createElement('div');
    l.className = 'wc-stat-lbl';
    l.textContent = lbl;
    box.appendChild(v);
    box.appendChild(l);
    return box;
  }

  function renderDetail(idx) {
    var seg = segments[idx];
    var d   = seg.dynamics || {};
    var t   = seg.target   || null;

    // Compliance colour for in-zone value
    var comp = 'muted';
    if (t) {
      if (seg.avg_power > t.max_w)      comp = 'above';
      else if (seg.avg_power < t.min_w) comp = 'below';
      else                               comp = 'in';
    }

    document.getElementById('wc-d-name').textContent = seg.name;
    document.getElementById('wc-d-type').textContent = seg.type || '';

    // Stats grid — 3×3, order: Duration, Distance, Pace, Avg Power, Target, Avg HR, Cadence, Step Length, GCT
    var statsEl = document.getElementById('wc-d-stats');
    while (statsEl.firstChild) statsEl.removeChild(statsEl.firstChild);

    statsEl.appendChild(mkStatBox(
      seg.duration_min != null ? seg.duration_min.toFixed(1) + ' min' : '—',
      'Duration'));
    statsEl.appendChild(mkStatBox(
      seg.distance_km != null ? seg.distance_km.toFixed(2) + ' km' : '—',
      'Distance'));
    statsEl.appendChild(mkStatBox(
      fmtPace(seg.duration_min, seg.distance_km),
      'Avg Pace'));
    statsEl.appendChild(mkStatBox(
      seg.avg_power != null ? Math.round(seg.avg_power) + ' W' : '—',
      'Avg Power'));
    statsEl.appendChild(mkStatBox(
      t ? t.min_w + '–' + t.max_w + ' W' : '—',
      'Target', t ? null : 'muted'));
    statsEl.appendChild(mkStatBox(
      seg.avg_hr != null ? Math.round(seg.avg_hr) + ' bpm' : '—',
      'Avg HR'));
    statsEl.appendChild(mkStatBox(
      d.cadence_med     ? d.cadence_med + ' spm'     : '—',
      'Cadence',     d.cadence_med     ? null : 'muted'));
    statsEl.appendChild(mkStatBox(
      d.step_length_med ? d.step_length_med + ' m'   : '—',
      'Step Length', d.step_length_med ? null : 'muted'));
    statsEl.appendChild(mkStatBox(
      d.gct_med         ? d.gct_med + ' ms'          : '—',
      'GCT',         d.gct_med         ? null : 'muted'));

    // Strips
    var stripsEl = document.getElementById('wc-d-strips');
    while (stripsEl.firstChild) stripsEl.removeChild(stripsEl.firstChild);

    // Compliance strip
    var cs = document.createElement('div');
    cs.className = 'wc-detail-strip';
    if (t) {
      if (t.pct_time_below > 0) {
        var b = document.createElement('div');
        b.className = 'cs-below'; b.style.width = Math.round(t.pct_time_below) + '%';
        cs.appendChild(b);
      }
      if (t.pct_time_in_range > 0) {
        var n = document.createElement('div');
        n.className = 'cs-in'; n.style.width = Math.round(t.pct_time_in_range) + '%';
        cs.appendChild(n);
      }
      if (t.pct_time_above > 0) {
        var a = document.createElement('div');
        a.className = 'cs-above'; a.style.width = Math.round(t.pct_time_above) + '%';
        cs.appendChild(a);
      }
    } else {
      var none = document.createElement('div');
      none.className = 'cs-none'; none.textContent = 'no target';
      cs.appendChild(none);
    }
    stripsEl.appendChild(cs);

    // HR zone strip
    var hr = document.createElement('div');
    hr.className = 'wc-detail-strip wc-detail-strip--hr';
    var hz = seg.hr_zones || {};
    var zoneKeys = ['Z1_pct', 'Z2_pct', 'Z3_pct', 'Z4_pct', 'Z5_pct'];
    zoneKeys.forEach(function (key, zi) {
      var pct = hz[key] || 0;
      if (pct <= 0) return;
      var el = document.createElement('div');
      el.className = 'wc-hz wc-hz' + (zi + 1);
      el.style.width = pct.toFixed(1) + '%';
      var s = document.createElement('span');
      s.textContent = 'Z' + (zi + 1);
      el.appendChild(s);
      hr.appendChild(el);
    });
    stripsEl.appendChild(hr);

    // Dot nav
    var footer = document.getElementById('wc-d-footer');
    while (footer.firstChild) footer.removeChild(footer.firstChild);
    segments.forEach(function (_, si) {
      var dot = document.createElement('div');
      dot.className = 'wc-seg-dot' + (si === idx ? ' wc-seg-dot--active' : '');
      (function (si) {
        dot.addEventListener('click', function (e) {
          e.stopPropagation();
          goToSeg(si);
        });
      })(si);
      footer.appendChild(dot);
    });
    var hint = document.createElement('span');
    hint.className = 'wc-swipe-hint';
    hint.textContent = '← swipe →';
    footer.appendChild(hint);
  }

  // Touch swipe
  var tX = 0, tY = 0, tMoved = false;
  detail.addEventListener('touchstart', function (e) {
    tX = e.touches[0].clientX; tY = e.touches[0].clientY; tMoved = false;
  }, { passive: true });
  detail.addEventListener('touchmove', function (e) {
    var dx = e.touches[0].clientX - tX, dy = e.touches[0].clientY - tY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 8) {
      tMoved = true;
      e.preventDefault();
    }
  }, { passive: false });
  detail.addEventListener('touchend', function (e) {
    if (!tMoved) return;
    var dx = e.changedTouches[0].clientX - tX;
    if (Math.abs(dx) > 40) {
      e.stopPropagation();
      if (dx < 0) goToSeg(currentSeg + 1);
      else        goToSeg(currentSeg - 1);
    }
    tMoved = false;
  });

  // Mouse drag (desktop)
  var mX = 0, mDown = false;
  detail.addEventListener('mousedown', function (e) { mX = e.clientX; mDown = true; });
  window.addEventListener('mouseup', function (e) {
    if (!mDown) return;
    mDown = false;
    var dx = e.clientX - mX;
    if (Math.abs(dx) > 40 && detail.classList.contains('wc-phase-open')) {
      e.stopPropagation();
      if (dx < 0) goToSeg(currentSeg + 1);
      else        goToSeg(currentSeg - 1);
    }
  });
})();
</script>
```

- [ ] **Step 2: Run the tests**

```bash
source .venv/bin/activate && pytest tests/test_web.py::TestWorkoutChart -v
```
Expected: all pass.

- [ ] **Step 3: Run the full test suite**

```bash
source .venv/bin/activate && pytest -q
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add runcoach/web/templates/run_detail.html
git commit -m "feat: implement tap-to-flip workout segment detail interaction"
```

---

### Task 6: Manual smoke test

The E2E tests don't cover JS interactions, so a quick manual check is needed.

- [ ] **Step 1: Start the dev server**

```bash
source .venv/bin/activate && python -m runcoach.web
```

- [ ] **Step 2: Open a run detail page that has workout blocks**

Navigate to `http://localhost:5000` → pick any parsed run with workout blocks.

- [ ] **Step 3: Verify overview**
  - Chart renders with power bars, compliance strips, HR zone strips, segment names
  - No legend visible below the chart
  - Cursor is pointer on segment columns

- [ ] **Step 4: Tap/click a segment column**
  - Card flips to detail view
  - Stats grid shows 9 cells: Duration, Distance, Avg Pace, Avg Power, Target, Avg HR, Cadence, Step Length, GCT
  - Compliance strip and HR zone strip are full width at the bottom
  - Dot nav shows one dot per segment, active dot is orange
  - Page scrolled so card top is near viewport top

- [ ] **Step 5: Tap/click the detail card**
  - Card flips back to overview

- [ ] **Step 6: Tap a segment, then swipe left/right**
  - Content updates to next/previous segment
  - Active dot moves

- [ ] **Step 7: Test on mobile viewport or real device**
  - Repeat steps 3–6 with touch gestures
  - Confirm no tooltip appearing below the chart
