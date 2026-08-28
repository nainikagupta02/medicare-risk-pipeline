# Medicare Member Risk & Utilization Forecasting

Member-level risk stratification for future healthcare cost and utilization,
built on CMS DE-SynPUF synthetic claims data.

## Objective and key results

**Objective:** Reduce avoidable high-cost utilization among Medicare
members through proactive, risk-based care management — rather than
reactive, cost-driven targeting after spend has already happened.

| Key result | Target | Actual |
|---|---|---|
| Deploy a risk model predicting 2010 high-cost outcomes from 2008-2009 claims, AUC ≥ 0.70 | ≥ 0.70 | **0.718** (5-fold CV, XGBoost/LightGBM, early-stopped) |
| Beat naive prior-year-spend targeting, not just random, at realistic capacity | ≥ 1.5x spend captured | **2.0x** at top 1% capacity, 1.2x at top 10% |
| Ship an interpretable, stakeholder-facing decision tool — not a model scorecard | plain-language drivers, no raw AUC/SHAP on the main view | **4-page dashboard** (Dash + Tableau), SHAP translated to plain-language drivers |
| Check the model's fairness across demographic subgroups before considering deployment | no majority-group advantage on standard metrics | **confirmed** — Black members' AUC/AP/recall were the *highest* of any group; the finer decile-matched check is honestly inconclusive at this sample size (see below) |
| Make risk output consumable by downstream clinical/care systems, not siloed in a dashboard | valid FHIR R4 export | **52,375/52,375** resources exported with 0 validation errors; live round-trip verified against a public FHIR test server |

Every number above is a real, already-computed result from this repo, not
an aspirational placeholder — each links to the section below that produced
it.

## Pipeline

```
Claims (DE-SynPUF)
  -> SQL/ETL (sql/, notebooks/01_etl_load_raw.ipynb)
  -> Cohort construction (sql/cohort/, notebooks/02_build_cohort.ipynb)
  -> Feature engineering + labels (sql/features/, notebooks/03_build_features_and_labels.ipynb)
  -> Exploratory data analysis (notebooks/04_exploratory_data_analysis.ipynb)
  -> Models: Logistic Regression + XGBoost (notebooks/05_train_models.ipynb)
  -> Explainability: SHAP (notebooks/06_shap_explainability.ipynb)
  -> Forecasting: ARIMA + seasonal-naive baseline (notebooks/07_arima_forecasting.ipynb)
  -> Care management targeting simulation (notebooks/08_care_management_targeting.ipynb)
  -> Fairness / subgroup analysis (notebooks/09_fairness_and_subgroup_analysis.ipynb)
  -> Cost regression: predicting the dollar amount, not just high/low (notebooks/10_cost_regression.ipynb)
  -> Payer / value-based-care dashboard (dashboard/)
```

Run the notebooks in numeric order — each one reads what the previous one
wrote to `data/interim/` or `data/processed/`.

## Results (Sample 1, `high_cost` label)

`high_cost` is the top decile of 2010 Medicare spend — but the 90th-percentile
dollar threshold is derived **only from the training split** (frozen, then
applied unchanged to the test set), not from the full cohort. Computing it
from the full cohort first would let the test set's own outcome distribution
quietly influence where the label boundary falls — a mild form of leakage,
worth avoiding even though the numerical effect here turned out to be tiny.
5-fold CV is likewise run only within the training partition; the test set is
touched exactly once, at the very end. See `notebooks/05_train_models.ipynb`.

5-fold cross-validated performance — the number worth citing, not any single
train/test split (which moved by ~0.02 AUC run to run on the same data):

| model | AUC | average precision |
|---|---|---|
| Logistic Regression (log1p-transformed skewed features) | 0.716 ± 0.006 | 0.225 ± 0.011 |
| XGBoost (early-stopped) | 0.718 ± 0.008 | 0.251 ± 0.014 |
| LightGBM (early-stopped) | 0.718 ± 0.008 | 0.253 ± 0.014 |

All three now land within noise of each other on AUC — closer than before,
because XGBoost and LightGBM were originally overfitting (see **Overfitting
check** below); fixing that removed what had been an artificial gap. Both
tree models still edge out Logistic Regression on average precision (the
metric that matters more given the ~90/10 label imbalance), even after
log-transforming Logistic Regression's skewed inputs.

**Overfitting check, and what actually fixed it.** Every metric above is
test-set-only; comparing to train-set performance is the direct way to catch
a model memorizing training data rather than generalizing. An ablation
tested the obvious levers: removing `scale_pos_weight` entirely, or adding
L1/L2 regularization, barely moved the gap (0.072 → ~0.06). What did move it
was tree capacity — `max_depth=3` alone cut it in half, and **early
stopping** (holding out a validation slice from the training partition to
pick the round count, then refitting on the full training partition at that
fixed count) did best of all, *improving* test AUC while shrinking the gap —
the tell that the extra rounds were fitting noise, not signal:

| model | train AUC | test AUC | gap |
|---|---|---|---|
| Logistic Regression | 0.719 | 0.725 | −0.006 |
| XGBoost (300 fixed rounds → early-stopped to 97) | 0.794 → 0.745 | 0.722 → 0.726 | 0.072 → **0.019** |
| LightGBM (300 fixed rounds → early-stopped to 76) | — → 0.741 | — → 0.725 | — → **0.015** |

One real bug surfaced while wiring this up: LightGBM's classifier
automatically registers `binary_logloss` (from its default objective) as an
eval metric alongside whatever's passed to `.fit()`'s `eval_metric` — early
stopping tracked *that* one, which gets monotonically worse every round on
this data, so it "stopped" at round 1 every time until `metric="auc"` was
set on the constructor itself, not just passed to `.fit()`. Caught by
printing the actual per-round validation trajectory rather than trusting
`best_iteration_` silently. See `notebooks/05_train_models.ipynb`.

**Care-management targeting — and does the model actually earn its keep?**
Three strategies were compared at matched capacity: random selection, ranking
by prior-year spend alone (no model — the simplest thing a payer could
already be doing), and the trained model's risk score. At the top 1% of the
cohort (524 members):

| strategy | 2010 spend captured | share of total spend |
|---|---|---|
| Random | $1.5M | 1.0% |
| Prior-year spend (no model) | $4.2M | 2.7% |
| ML risk score | $8.6M | 5.5% |

That's **~5.7x the spend captured vs. random, and ~2.0x vs. the naive
prior-spend heuristic** — the second number is the one that actually
justifies building a model instead of just sorting by last year's bill. Lift
narrows at larger capacities (~1.2x vs. prior-spend at 10%), as expected —
targeting matters most when capacity is scarce.

## Fairness and subgroup analysis

`high_cost` is a proxy for health need — it's *spend*, not illness itself. A
2019 *Science* paper (Obermeyer et al.) found a widely-used commercial
healthcare risk algorithm was racially biased for exactly this reason: cost
reflects access to care as much as need, and at the same predicted risk
score, Black patients in that study turned out to have more untreated
illness than white patients. This project makes the same modeling choice, so
`notebooks/09_fairness_and_subgroup_analysis.ipynb` checks for the same
pattern on the held-out test set (never the training data):

- **Standard metrics show no disparity favoring the majority group** — Black
  members' AUC (0.741), average precision (0.294), and recall at the top-10%
  operating threshold (28.4%) were as good as or better than white members'
  (0.734 / 0.263 / 26.6%).
- **The decile-matched check uses three independent need proxies, not just
  spend** — comparing realized 2010 spend alone is somewhat circular, since
  spend is literally what `high_cost` is built from. Two objective,
  non-circular proxies were added: `condition_burden_2010` (a count of
  active chronic conditions straight from CMS's own flags) and
  `inpatient_admits_2010` (hospitalizations). **All three land in the same
  place** — Black members' realized need was higher than white members' at
  the same predicted-risk decile in 5 of 10 deciles for spend, 4 of 10 for
  condition count, 6 of 10 for admits — no proxy shows a clean,
  one-directional signal, and all three swing widely decile to decile
  (condition burden: −11% to +75%; admits: −14% to +104%).

That agreement across three differently-sourced proxies (dollar, clinical,
utilization) is itself informative — it's not that the spend-based check
happened to be noisy while a cleaner signal was hiding in the objective
clinical data; all three are noisy in the same way, consistent with genuine
sample-size limitation rather than a missed signal. With Sample 1's ~1,000
Black members split across 10 deciles (~100 per cell), that's expected, not
surprising. The honest result is that the check is inconclusive, not that it
resolved cleanly in either direction — a real deployment on the full,
non-synthetic population, with enough sample size per decile to actually
resolve the question, would need to rerun this before trusting either
conclusion.

## Cost regression: predicting the dollar amount

The classifiers answer *who* — a binary `high_cost` flag. Notebook 10 adds
*how much* — a continuous prediction of each member's actual 2010 spend,
complementary to (not a replacement for) the classifier: the flag stays the
primary targeting mechanism, while regression enables a cohort-level budget
forecast the classifier structurally cannot produce.

**R² is low across every model (0.03–0.13)** — meaningfully lower than the
classifier's AUC — because predicting an *exact dollar amount* is a much
harder task than ranking members above/below a threshold, especially with
the same coarse feature set (see **Next steps**).

**The real finding was about which loss function to use, not which library.**
The standard approach — train on `log1p(total_paid_2010)`, `expm1()` the
predictions back to dollars — is what most guidance recommends trying first,
and it's what got tried first here. But it has a known problem called
**retransformation bias**: exponentiating predictions from a model trained on
the log scale systematically *underestimates* the true dollar-scale total
when the underlying data is this skewed. It wasn't a theoretical concern —
it showed up directly: summing the log1p model's predictions across the test
set landed **53% below** actual total spend ($14.5M predicted vs. $31.1M
actual). Switching to **Tweedie regression** (trained directly on raw
dollars — the actual industry-standard loss function for zero-inflated,
right-skewed insurance/actuarial cost data, not just a random alternative to
try) fixed both problems at once:

| | R² | Total spend forecast error |
|---|---|---|
| LightGBM, log1p target | 0.034 | **-53.2%** |
| **LightGBM, Tweedie (selected)** | **0.132** | **-2.0%** |

A model-selection bug caught this the hard way: the notebook's first pass
picked the final saved model *before* the Tweedie comparison even ran,
so the initial version shipped the more biased log1p model despite the
better option sitting one cell later. Fixed by reordering the notebook so
model selection happens after every candidate (including both Tweedie
variants) has been scored, and picking by R² — the same discipline as
everywhere else in this project: don't trust a number until it's been
checked against the alternative, and don't ship the first thing that runs
without comparing it to what else was tried.

## Dashboard

`dashboard/app.py` is a stakeholder-facing decision tool, not a model
scorecard — no AUC/F1/SHAP-beeswarm on the main views. Four pages, reading
pre-computed artifacts from `data/processed/` (no live model inference):

1. **Executive Overview** — cohort size, high-cost rate, total spend, and the
   top-1%-vs-random lift, in ~20 seconds.
2. **Risk & Targeting** — a capacity selector (top 1%/5%/10%) driving the
   random vs. prior-spend vs. ML-risk-score comparison live.
3. **What Drives Risk** — SHAP importance translated into plain-language
   driver names (e.g. "Congestive heart failure," not `has_chf`), plus
   average risk by chronic condition.
4. **Spend Trends** — the ARIMA forecast, with the CMS-documented
   data-completeness caveat shown as a visible on-chart warning, not buried
   in a README — the forward forecast actually goes negative by mid-2011,
   which is itself self-evident proof the trend being extrapolated is an
   artifact, not real.

Run with `python dashboard/app.py` after the notebooks have populated
`data/processed/`.

**Tableau alternative:** `tableau/` has a `export_for_tableau.py` script
(produces 5 Tableau-friendly CSVs from the same pipeline outputs) and a
`BUILD_GUIDE.md` walking through building the same 4-page dashboard in
Tableau Public/Desktop — sheet by sheet, field by field, with the exact
calculated fields and parameter setup needed. Tableau workbooks are
GUI-authored, not scriptable, so that guide is meant to be followed by hand
rather than run.

## Interoperability: FHIR export

A risk score sitting only in a payer-side dashboard isn't usable by a
provider's EHR — CMS's Interoperability and Patient Access rule requires
Medicare Advantage plans to expose exactly this kind of data via FHIR.
`fhir/export_fhir_risk_assessments.py` converts every member's risk score
into a standard **FHIR R4 `RiskAssessment`** resource (the field built
specifically for "predicted outcome + probability + basis"), paired with a
minimal `Patient` resource as its subject reference:

```bash
python fhir/export_fhir_risk_assessments.py            # full cohort
python fhir/export_fhir_risk_assessments.py --sample 10 # quick test run
```

- `probabilityDecimal` — the model's risk score
- `qualitativeRisk` — the risk tier (low/medium/high/very high)
- `rationale` — the member's top SHAP drivers in plain language (e.g.
  "increased by: prior-year hospital spending, congestive heart failure")
- Every resource carries an explicit `note` disclaiming that the underlying
  member is CMS's synthetic DE-SynPUF data, not a real patient

All 52,375 members exported clean (0 schema-validation errors) via the
`fhir.resources` library's pydantic models, written as NDJSON — the standard
FHIR Bulk Data Export format — to `fhir/output/` (gitignored, regenerate
with the script above). Scoped deliberately to `RiskAssessment` + `Patient`
only, not a full resource graph (`Condition`/`Encounter`/`Claim` references
as formal `basis`) — that would be a much larger undertaking for no added
interoperability value over what this project actually demonstrates.

**Verified against a live FHIR server, not just schema validation:**
`fhir/post_to_test_server.py` PUTs a handful of the exported resources to
[hapi.fhir.org](https://hapi.fhir.org/baseR4) — a public FHIR R4 test
sandbox built for exactly this — then GETs them back to confirm the server
actually accepted and persisted them (not just that they validated
locally). Run: 5/5 `PUT`s and 5/5 `GET`s succeeded, with the retrieved
`probabilityDecimal` and `rationale` matching exactly what was sent. Only
ever point this at a public *test* server with synthetic data, as here —
never at a real FHIR endpoint holding real patient data.

## Data

Download CMS DE-SynPUF sample files (Beneficiary Summary, Inpatient, Outpatient,
Carrier Claims, Prescription Drug Events) into `data/raw/`. See
`configs/data_sources.yaml` for expected file names and the source URL.

DE-SynPUF is a *synthetic* claims dataset — CMS statistically simulates
realistic claims patterns from real Medicare data so no record maps back to
an actual beneficiary. It's a stand-in for practice/portfolio work, not a
source for real clinical or policy conclusions.

Raw files are never committed — `data/` is gitignored except for `.gitkeep`
markers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook notebooks/
```

### Docker (alternative)

```bash
docker build -t medicare-pipeline .
docker run -p 8888:8888 -v "$(pwd)/data:/app/data" medicare-pipeline
```

Then open `http://localhost:8888/notebooks/notebooks/` (auth is disabled for
local convenience — don't expose this container to an untrusted network
without adding it back). The `-v` mount keeps the ~2GB of raw/interim/
processed data on the host instead of baking it into the image; download the
DE-SynPUF files into `data/raw/` on the host first (see **Data** above).

**Actually build-tested, not just written** — three real issues only
surfaced once this was run in a genuinely clean environment, not assumed
away:
- `pyyaml==5.4.1` fails to build from source on Python 3.11 (a known
  PyYAML/Cython incompatibility) — bumped to `6.0.3`.
- `pyarrow` was missing entirely — it came bundled with the local Anaconda
  dev environment for free, so its absence in `requirements.txt` went
  unnoticed until a clean container needed it for Parquet I/O.
- **Needs ~12GB+ of memory allocated to Docker Desktop.** Notebook 01 loads
  the full Carrier Claims CSV (4.7M rows × 142 columns) into memory at
  once; Docker Desktop's 8GB default got OOM-killed partway through (memory
  climbed to the VM's ceiling, then the kernel died with no traceback —
  confirmed by watching `docker stats` live during the crash). Bumped to
  16GB (Docker Desktop → Settings → Resources → Memory) and it ran clean.
  On macOS, Docker also needs Desktop-folder access explicitly granted
  (System Settings → Privacy & Security → Files and Folders) before the
  `-v` mount above will work at all.

With those three fixes, the full image builds, the container runs, and
notebook 01 executes end to end against the real 8-file DE-SynPUF Sample 1
producing correct output — verified directly, not assumed.

## Known limitations

- **Cohort definition uses hindsight.** The cohort requires full-year 2010
  coverage and being alive through the end of 2010 — both facts you can only
  know in retrospect. A genuinely prospective model (like CMS's real HCC
  risk adjustment) would define the cohort using only what's known before
  the prediction year starts (end of 2009), then score everyone and let
  mid-year deaths/disenrollments fall out of the label naturally. What's
  built here is a retrospective research cohort — standard for a methodology
  demo, but it means reported performance is somewhat optimistic relative to
  a live deployment, where you can't yet know who'll survive/stay enrolled
  the whole year.
- **No true leakage from 2010 into the features** — every predictor is
  computed from date-filtered 2008–2009 SQL, the two labels are computed
  from a separately-run 2010 aggregate, and `FEATURE_COLS` (notebooks
  05/06/08) explicitly excludes `total_paid_2010` / `inpatient_admits_2010`
  even though they live in the same saved table. See the "guardrail" note at
  the end of `04_exploratory_data_analysis.ipynb` — those two columns
  correlate highly with the labels *because they define them*, and it's
  worth double-checking they never get added to a feature list by mistake.
- **A few DE-SynPUF fields go negative** (`inpatient_paid`, `total_paid_2010`,
  etc.) — a small number of rows, from claim adjustments/reversals in the
  source data, not a pipeline bug. Doesn't affect the percentile-based
  labels, but worth knowing if you inspect individual rows.
- **Real multicollinearity between claim counts and their own dollar
  amounts** (e.g. `carrier_claims` vs `carrier_paid`, r≈0.94) — expected,
  doesn't hurt XGBoost, but makes individual Logistic Regression
  coefficients hard to interpret in isolation.
- **2010 claim volume is artificially low — confirmed by CMS, not just
  inferred.** Every claim type declines steadily through 2010 in the monthly
  series used for forecasting, accelerating sharply toward December (total
  cohort spend goes from ~$23M/month in 2008–2009 down to ~$3.9M in
  December 2010, an ~83% drop) — even though the cohort is fixed (everyone
  is enrolled and alive through all of 2010 by construction, so this can't
  be attrition out of the population). CMS's own *DE-SynPUF User Manual*
  (Table 1) states 2010 claim counts are lower across the full population
  too, attributing it to "attrition from death and some effects of
  disclosure treatment" (CMS's privacy-preserving synthesis process, which
  appears to thin data more aggressively in the file's final year). Since
  this cohort already excludes death attrition, the decline seen here is
  most likely almost entirely that synthesis artifact. The ARIMA notebook
  (07) doesn't correct for it, so its strong backtest result (MAE $2.3M vs.
  $13.5M for seasonal-naive) should be read as a demonstration of the
  method, not proof ARIMA would forecast genuinely complete data this well.

## Lessons learned

- **Raw CMS column casing silently breaks joins.** DE-SynPUF ships ALL-CAPS
  headers that DuckDB/pandas preserve as-is; every lowercase SQL reference
  failed at merge time until columns were normalized once during ETL,
  instead of re-aliased in every downstream query.
- **Multi-year source files need explicit year tagging.** Beneficiary
  Summary has one row per beneficiary *per year* (2008/2009/2010 are
  separate files); concatenating them into a single table without a year
  column silently triples every beneficiary's row count downstream.
- **Never join multiple raw fact tables before aggregating.** Joining
  Inpatient, Outpatient, and Carrier claims directly on member ID fans out —
  a member with 5 inpatient and 100 carrier claims produces 500 joined rows,
  multiplying every sum. Each claim type has to be pre-aggregated to one row
  per member first.
- **Line-level claim files need their own aggregation logic.** Carrier
  Claims has no single payment column, only 13 separate `LINE_NCH_PMT_AMT_n`
  fields per claim — assuming it matched Inpatient/Outpatient's single
  `CLM_PMT_AMT` pattern threw a SQL error immediately, the lucky outcome
  compared to silently wrong numbers.
- **A single train/test split isn't a number worth reporting.** Re-running
  the same pipeline moved AUC by ~0.02 (0.706 → 0.723) purely from a
  different random partition; 5-fold cross-validation (0.715 ± 0.004) was
  the number that actually held up run to run.
- **Class imbalance handling doesn't transfer between model families.**
  `class_weight="balanced"` fixes Logistic Regression but does nothing for
  XGBoost, which needs its own `scale_pos_weight` — adding it lifted
  minority-class recall from near-zero to 54–67%, at the cost of roughly
  doubling the Brier score (calibration got worse as recall improved).
- **Tree models tolerate what breaks linear models, for free.** XGBoost and
  LightGBM needed no preprocessing for the heavily right-skewed cost and
  utilization features; Logistic Regression needed a log1p transform just
  to be competitive — and that transform itself produced `NaN` on the
  handful of negative claim-adjustment values until explicitly clipped.
- **When a number looks wrong, check the data provider's own docs before
  assuming a pipeline bug.** An ~83% drop in monthly claims volume toward
  the end of 2010 looked like an ETL error; CMS's own DE-SynPUF user manual
  confirmed it's a documented synthesis artifact ("attrition from death and
  some effects of disclosure treatment"), not something to fix in code.
- **Forecasting without a real future needs an honest backtest.** With data
  ending in 2010, the only way to validate ARIMA against a seasonal-naive
  baseline was holding out the last 6 months and comparing forecasts to
  what actually happened — not fitting on everything and calling the output
  a trustworthy forecast.
- **A percentile-based label needs its threshold frozen from training data
  only.** Computing the 90th-percentile cutoff from the full cohort before
  splitting lets the test set's own outcome distribution influence where the
  label boundary falls — split first, derive the threshold from training
  rows only, then apply that one frozen number to both sides. The numerical
  effect here was tiny (the threshold barely moved), but the discipline is
  the same regardless of magnitude, and it has to happen before cross-
  validation too, not just before the final test evaluation.
- **A model's own metrics rarely persuade a stakeholder — a naive baseline
  does.** AUC 0.71 says little to a payer; "captures 2.1x more spend than
  just ranking by last year's bill" says everything, because it directly
  answers whether the model earns its complexity over what they could
  already be doing without one.

## Next steps

**Diagnosis-code feature enrichment — the highest-leverage remaining lever.**
The current 27 features are coarse: 12 broad chronic-condition flags
(`has_diabetes`, `has_chf`, etc.) and a handful of utilization/spend counts,
none of which distinguish severity. A member with mild, diet-controlled
diabetes gets the identical `has_diabetes=1` flag as one with diabetic
kidney failure; a routine annual wellness visit and a complex surgical
procedure both just count as "1 carrier claim." The raw claims files
already carry much finer detail that's currently unused:

- `ICD9_DGNS_CD_1-10` (up to 10 diagnosis codes per claim) — would need
  grouping via CCS (Clinical Classifications Software, a standard
  NIH-maintained mapping from ~14,000 ICD-9 codes down to ~285 clinically
  meaningful categories) rather than used raw, since ICD-9 codes alone are
  too high-cardinality and sparse to feed a model directly
- `HCPCS_CD_*` procedure/service codes — what kind of visit or procedure
  each claim actually was, not just that one happened
- `CLM_DRG_CD` (Diagnosis Related Group) — CMS's own severity/billing
  category for each inpatient stay, currently ignored entirely

**Why this over further model tuning:** a 100-trial Optuna search over
XGBoost's hyperparameters (max_depth, learning_rate, subsample,
colsample_bytree, reg_alpha, reg_lambda, min_child_weight) found essentially
nothing — 0.7162 vs. the hand-tuned baseline's 0.7156 CV AUC, a difference
smaller than the ±0.007 noise floor across folds. That's consistent with the
EDA finding that no single feature correlates with `high_cost` above r≈0.23
— the model isn't underfit from bad hyperparameters, it's close to the
ceiling of what a dozen broad flags and a few counts can tell it. This is
also exactly why real Medicare risk-adjustment models (CMS's own HCC model,
which this project loosely echoes) use hundreds of diagnosis-code-derived
categories rather than a handful of condition flags — that granularity is
where the real signal lives.

**Other open items, roughly in priority order:**
- A stricter, genuinely prospective cohort definition (enrollment/survival
  known only as of the *start* of the prediction year, not the hindsight
  version currently used — see **Known limitations**).
- Wire `member_cost_predictions.parquet` (notebook 10's output) into the
  dashboard/Tableau exports alongside the existing risk score/tier — not yet
  done, the regression model exists but its predictions aren't surfaced
  anywhere outside the notebook yet.
- Verify the Dockerfile builds/runs on Windows and Linux hosts — already
  build-tested on macOS + Apple Silicon (see **Docker**), those two are not.

## Project layout

- `data/raw` — untouched source extracts (DE-SynPUF CSVs)
- `data/interim` — cleaned/typed tables, one step above raw
- `data/processed` — cohort, feature, model, and forecast outputs
- `sql/cohort` — cohort inclusion/exclusion logic
- `sql/features` — feature-generating SQL (utilization, spend, chronic conditions)
- `notebooks` — the pipeline itself, one notebook per stage (ETL through fairness analysis)
- `dashboard` — the 4-page stakeholder decision dashboard (see **Dashboard** above)
- `reports/figures` — exported charts for write-ups
- `configs` — YAML configs (paths, model hyperparameters, cohort windows)
