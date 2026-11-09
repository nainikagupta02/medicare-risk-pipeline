# Tableau Build Guide

**Live dashboard:** https://public.tableau.com/app/profile/nainika.gupta/viz/MedicareMemberRiskStratification/Story1

Mirrors `dashboard/app.py`'s 4-page structure. Each section names the sheet
to build, which fields go on which shelf, and any calculated fields or
parameters needed. Built for **Tableau Public** (free) or Tableau Desktop —
both use the same authoring UI.

## Setup

1. Run `python tableau/export_for_tableau.py` (after the notebooks have
   populated `data/processed/`) to produce the 5 CSVs in `tableau/data/`.
2. Open Tableau Public / Desktop → **Connect → Text File** → select all 5
   CSVs from `tableau/data/` as separate data sources (no need to join them —
   each page uses one source, except page 3 which uses two).
3. Create one new **Dashboard** per page below (Dashboard menu → New
   Dashboard), then a **Sheet** per chart, and drag sheets onto the
   dashboard.

---

## Page 1 — Executive Overview

**Data source:** `member_risk_scores.csv` + `targeting_comparison.csv`

**KPI tiles** (4 separate sheets, each a single "Text" table with one big
number — Format → font size ~36pt):

| Tile | Calculated field | Formula |
|---|---|---|
| Members analyzed | — | `COUNTD([Desynpuf Id])` on `member_risk_scores` |
| High-cost rate | `High Cost Rate` | `AVG([High Cost Frozen])` — format as Percentage |
| 2010 total spend | — | `SUM([Total Paid 2010])` — format as Currency, abbreviated (right-click axis → Format → Numbers → Currency (Custom) → millions) |
| Lift, top 1% vs random | `Lift Top1` | See below |

For **Lift Top1**, add this calculated field on `targeting_comparison`:

```
// Lift Top1
IF [Capacity Pct] = 0.01 THEN
    LOOKUP(SUM(IF [Strategy] = "ml_risk_score" THEN [Spend Share] END), 0)
    / LOOKUP(SUM(IF [Strategy] = "random" THEN [Spend Share] END), 0)
END
```
(Simplest robust approach: since `targeting_comparison.csv` has only 9 rows,
just eyeball the two `spend_share` values for `capacity_pct = 0.01` and
hardcode a single-value calculated field, e.g. `5.9` — this is a static KPI
tile, not something that needs to recompute live.)

**Chart — "2010 spend by risk tier"** (horizontal bar, on `member_risk_scores`):
- Rows: `Risk Tier`
- Columns: `SUM([Total Paid 2010])`
- Color: `Risk Tier` — set a custom diverging-severity palette: low = green
  (`#0ca30c`), medium = yellow (`#fab219`), high = orange (`#ec835a`),
  very_high = red (`#d03b3b`) — right-click the color legend → Edit Colors →
  assign each value.
- Sort: manually order low → medium → high → very_high (right-click axis →
  Sort → order).
- Label: turn on "Show mark labels," format as Currency abbreviated.

---

## Page 2 — Risk & Targeting

**Data source:** `targeting_comparison.csv`

**Parameter — the capacity selector:**
1. Right-click in the Data pane → **Create Parameter**.
2. Name: `Capacity Selector`. Data type: Float. Allowable values: List —
   add `0.01` (display "Top 1%"), `0.05` ("Top 5%"), `0.10` ("Top 10%").
3. Right-click the parameter → **Show Parameter Control** (adds a dropdown
   to the view).

**Filter the view to the selected capacity:**
- Create a calculated field `Selected Capacity`:
  ```
  [Capacity Pct] = [Capacity Selector]
  ```
- Drag `Selected Capacity` to the Filters shelf, filter to `True`.

**Chart — "Spend captured by strategy"** (bar chart):
- Rows: `Strategy Label`
- Columns: `SUM([Spend Captured])`
- Color: `Strategy Label` — Random = gray (`#898781`), Prior-year spend =
  orange (`#eb6834`), ML risk score = blue (`#2a78d6`)
- Label: mark labels on, Currency format

**KPI tiles below the chart** (all filtered by the same `Selected Capacity`
filter, so they update when the parameter changes):
- Members targeted: `SUM([Members Targeted])` where `Strategy = "ml_risk_score"`
- Spend captured: `SUM([Spend Captured])` where `Strategy = "ml_risk_score"`
- Lift vs. random / Lift vs. prior-spend: two calculated fields dividing the
  ML row's `Spend Share` by the Random row's / Prior-year row's `Spend
  Share`, using `LOOKUP` or a `FIXED` LOD expression, e.g.:
  ```
  // Lift vs Random
  SUM(IF [Strategy] = "ml_risk_score" THEN [Spend Share] END)
  / SUM(IF [Strategy] = "random" THEN [Spend Share] END)
  ```
  (Table calc — set "Compute using" to the `Strategy` field so it divides
  across the strategy rows within the current capacity filter.)

---

## Page 3 — What Drives Risk

**Data source A:** `shap_driver_importance.csv`

**Chart — "Top drivers of predicted risk"** (horizontal bar):
- Rows: `Driver`, sorted descending by `Mean Abs Shap`
- Columns: `SUM([Mean Abs Shap])`
- Filter: keep only the top 8 (right-click `Driver` → Filter → Top → By
  field → Top 8 by `Sum(Mean Abs Shap)`)
- Color: single blue (`#2a78d6`) — one series, no legend needed
- Turn off the x-axis (it's a relative-influence scale, not a dollar/count
  value) — label bars directly instead

**Data source B:** `condition_avg_risk.csv`

**Table — "Average predicted risk by chronic condition"**:
- Rows: `Condition`, sorted descending by `Avg Risk With Condition`
- Columns: `AVG([Avg Risk With Condition])`, `AVG([Avg Risk Without Condition])`
- Format both as Percentage
- This is a plain crosstab (Sheet → Show Me → text table), not a chart

---

## Page 4 — Spend Trends

**Data source:** `monthly_spend_trend.csv`

**Chart — "Monthly Medicare spend, actual and forecast"** (line chart):
- Columns: `Period` (as a discrete dimension, or convert to a Date via
  a calculated field `DATE([Period] + "-01")` for a continuous date axis)
- Rows: `SUM([Value])`
- Color: `Series` — Actual = blue (`#2a78d6`), ARIMA forecast = orange
  (`#eb6834`), dashed line for the forecast series (right-click the ARIMA
  line → Format → Lines → Dash pattern)

**The data-quality callout — do this as a Dashboard object, not a chart:**
1. In the Dashboard view, drag a **Text** object below the chart.
2. Paste this text and bold/color the first sentence red (`#d03b3b`):

   > ⚠ Data quality note: every claim type declines steadily through 2010,
   > and the forward forecast goes negative by mid-2011 (as low as -$6.4M) —
   > spend cannot be negative, which is itself proof this trend is an
   > artifact, not real. CMS's own DE-SynPUF documentation confirms 2010
   > claim volume is artificially suppressed ("attrition from death and
   > some effects of disclosure treatment"). This forecast is shown as a
   > demonstration of the ARIMA method, not a trustworthy prediction of
   > 2011 spend.

---

## Assembling the dashboards

For each of the 4 pages: **Dashboard → New Dashboard**, set size to
"Automatic," drag the relevant sheet(s) + KPI tiles + parameter control onto
the canvas, arrange with a **Tiled** layout (top row = KPI tiles side by
side, chart below). Then **Dashboard → New Story** (optional) to stitch all
4 pages into one navigable presentation with prev/next arrows — closest
Tableau equivalent to the Dash app's tabs.

## Publishing

**File → Save to Tableau Public** (or **Server → Publish Workbook** on
Desktop with a Tableau Server/Online account). Tableau Public hosts the
result at a public `public.tableau.com/views/...` URL, viewable by anyone
with the link, no login required — the standard way to share a portfolio
dashboard.
