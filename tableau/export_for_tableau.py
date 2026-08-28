"""Export clean, Tableau-friendly CSVs from the notebook pipeline's parquet
artifacts (data/processed/). Run once after notebooks 03/05/06/07/08 have
produced their outputs.

Mirrors the same 4-page structure as dashboard/app.py, so the Tableau build
follows the same story: Executive Overview, Risk & Targeting, What Drives
Risk, Spend Trends.

Usage:
    python tableau/export_for_tableau.py
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_LABELS = {
    "inpatient_admits": "Prior-year hospital admissions",
    "outpatient_visits": "Prior-year outpatient visits",
    "carrier_claims": "Prior-year specialist/physician visits",
    "inpatient_paid": "Prior-year hospital spending",
    "outpatient_paid": "Prior-year outpatient spending",
    "carrier_paid": "Prior-year physician/specialist spending",
    "has_alzheimers": "Alzheimer's / dementia",
    "has_chf": "Congestive heart failure",
    "has_ckd": "Chronic kidney disease",
    "has_cancer": "Cancer",
    "has_copd": "COPD",
    "has_depression": "Depression",
    "has_diabetes": "Diabetes",
    "has_ihd": "Ischemic heart disease",
    "has_osteoporosis": "Osteoporosis",
    "has_ra_oa": "Rheumatoid / osteoarthritis",
    "has_stroke_tia": "Stroke / TIA",
    "has_esrd": "End-stage renal disease",
    "age": "Age",
    "is_male": "Sex: male",
    "race_black": "Race: Black",
    "race_other": "Race: other",
    "race_hispanic": "Race: Hispanic",
    "rx_fill_count": "Prior-year prescription fills",
    "rx_total_cost": "Prior-year prescription spending",
    "rx_patient_paid": "Prior-year out-of-pocket Rx spending",
    "other_payer_paid": "Spending covered by another insurer",
}

CONDITION_COLS = [
    "has_chf", "has_diabetes", "has_ckd", "has_copd", "has_cancer",
    "has_alzheimers", "has_depression", "has_ihd", "has_osteoporosis",
    "has_ra_oa", "has_stroke_tia", "has_esrd",
]

# ------------------------------------------------ 1. member risk scores ----
member_scores = pd.read_parquet(DATA_DIR / "member_risk_scores.parquet")
member_scores.to_csv(OUT_DIR / "member_risk_scores.csv", index=False)
print(f"wrote member_risk_scores.csv ({len(member_scores):,} rows)")

# --------------------------------------------- 2. targeting comparison -----
targeting = pd.read_parquet(DATA_DIR / "targeting_comparison.parquet")
targeting["capacity_label"] = targeting["capacity_pct"].map({0.01: "Top 1%", 0.05: "Top 5%", 0.10: "Top 10%"})
targeting["strategy_label"] = targeting["strategy"].map({
    "random": "Random selection",
    "prior_year_spend": "Prior-year spend (no model)",
    "ml_risk_score": "ML risk score",
})
targeting.to_csv(OUT_DIR / "targeting_comparison.csv", index=False)
print(f"wrote targeting_comparison.csv ({len(targeting):,} rows)")

# ------------------------------------------------- 3. global SHAP driver ---
shap_values = pd.read_parquet(DATA_DIR / "xgboost_high_cost_shap_values.parquet")
global_importance = (
    shap_values.drop(columns="desynpuf_id").abs().mean().sort_values(ascending=False).reset_index()
)
global_importance.columns = ["feature", "mean_abs_shap"]
global_importance["driver"] = global_importance["feature"].map(FEATURE_LABELS)
global_importance.to_csv(OUT_DIR / "shap_driver_importance.csv", index=False)
print(f"wrote shap_driver_importance.csv ({len(global_importance)} rows)")

# --------------------------------------- 4. avg risk by chronic condition --
features = pd.read_parquet(DATA_DIR / "features_labeled.parquet")
members_df = features.merge(member_scores[["desynpuf_id", "risk_score"]], on="desynpuf_id")

rows = []
for col in CONDITION_COLS:
    rows.append({
        "condition": FEATURE_LABELS[col],
        "avg_risk_with_condition": members_df.loc[members_df[col] == 1, "risk_score"].mean(),
        "avg_risk_without_condition": members_df.loc[members_df[col] == 0, "risk_score"].mean(),
        "members_with_condition": int(members_df[col].sum()),
    })
condition_risk = pd.DataFrame(rows).sort_values("avg_risk_with_condition", ascending=False)
condition_risk.to_csv(OUT_DIR / "condition_avg_risk.csv", index=False)
print(f"wrote condition_avg_risk.csv ({len(condition_risk)} rows)")

# ------------------------------------------------- 5. monthly spend trend --
monthly = pd.read_parquet(DATA_DIR / "monthly_spend.parquet")
forecast = pd.read_parquet(DATA_DIR / "forecast_total_paid.parquet")

actual_long = monthly[["year_month", "total_paid"]].copy()
actual_long["period"] = pd.PeriodIndex(actual_long["year_month"].astype(str), freq="M").astype(str)
actual_long["series"] = "Actual"
actual_long = actual_long.rename(columns={"total_paid": "value"})[["period", "series", "value"]]

forecast_long = forecast.reset_index().rename(columns={"index": "period", "arima_forecast": "value"})
forecast_long["period"] = forecast_long["period"].astype(str)
forecast_long["series"] = "ARIMA forecast"
forecast_long = forecast_long[["period", "series", "value"]]

trend = pd.concat([actual_long, forecast_long], ignore_index=True)
trend.to_csv(OUT_DIR / "monthly_spend_trend.csv", index=False)
print(f"wrote monthly_spend_trend.csv ({len(trend)} rows)")

print("\ndone -- import these 5 CSVs into Tableau. See tableau/BUILD_GUIDE.md.")
