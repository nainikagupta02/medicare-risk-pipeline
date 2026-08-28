"""Export the trained model's per-member risk scores as FHIR R4
RiskAssessment resources -- the standard resource type for exactly this
("predicted outcome + probability + basis").

This is the realistic next step for this project: CMS's own Interoperability
and Patient Access rule requires Medicare Advantage plans to expose data
like this via FHIR, so a risk score living only in a payer-side dashboard
isn't actually usable by a provider's EHR system without this step.

Scope, deliberately: this produces a minimal `Patient` resource (just enough
to be a valid subject reference) and a `RiskAssessment` per member, with the
SHAP top drivers as free-text `rationale` -- not a full resource graph
(Condition/Encounter/Claim resources referenced as formal `basis`), which
would be a much larger undertaking with no added interoperability value for
what this project is actually demonstrating.

Every resource is tagged with an explicit disclaimer that the underlying
data is CMS's synthetic DE-SynPUF research file, not a real patient -- these
are not real people and must never be treated or presented as such.

Usage:
    python fhir/export_fhir_risk_assessments.py [--sample N]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from fhir.resources.annotation import Annotation
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.identifier import Identifier
from fhir.resources.patient import Patient
from fhir.resources.reference import Reference
from fhir.resources.riskassessment import RiskAssessment, RiskAssessmentPrediction

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYNTHETIC_DATA_DISCLAIMER = (
    "Generated from CMS's synthetic DE-SynPUF research dataset (Sample 1). "
    "This is NOT a real patient -- DESYNPUF_ID is a synthetic identifier "
    "with no relationship to any real Medicare beneficiary."
)

RISK_TIER_LABELS = {
    "low": "Low risk",
    "medium": "Medium risk",
    "high": "High risk",
    "very_high": "Very high risk",
}

FEATURE_LABELS = {
    "inpatient_admits": "prior-year hospital admissions",
    "outpatient_visits": "prior-year outpatient visits",
    "carrier_claims": "prior-year specialist/physician visits",
    "inpatient_paid": "prior-year hospital spending",
    "outpatient_paid": "prior-year outpatient spending",
    "carrier_paid": "prior-year physician/specialist spending",
    "has_alzheimers": "Alzheimer's / dementia",
    "has_chf": "congestive heart failure",
    "has_ckd": "chronic kidney disease",
    "has_cancer": "cancer",
    "has_copd": "COPD",
    "has_depression": "depression",
    "has_diabetes": "diabetes",
    "has_ihd": "ischemic heart disease",
    "has_osteoporosis": "osteoporosis",
    "has_ra_oa": "rheumatoid/osteoarthritis",
    "has_stroke_tia": "stroke/TIA",
    "has_esrd": "end-stage renal disease",
    "age": "age",
    "is_male": "sex: male",
    "race_black": "race: Black",
    "race_other": "race: other",
    "race_hispanic": "race: Hispanic",
    "rx_fill_count": "prior-year prescription fills",
    "rx_total_cost": "prior-year prescription spending",
    "rx_patient_paid": "prior-year out-of-pocket Rx spending",
    "other_payer_paid": "spending covered by another insurer",
}


def top_drivers_text(shap_row, n=3):
    """Turn one member's SHAP row into a short rationale string, e.g.
    'increased by: 4 prior hospital admissions, congestive heart failure;
    decreased by: age'."""
    contributions = shap_row.sort_values(key=lambda s: s.abs(), ascending=False).head(n)
    increases = [FEATURE_LABELS.get(f, f) for f, v in contributions.items() if v > 0]
    decreases = [FEATURE_LABELS.get(f, f) for f, v in contributions.items() if v < 0]
    parts = []
    if increases:
        parts.append("increased by: " + ", ".join(increases))
    if decreases:
        parts.append("decreased by: " + ", ".join(decreases))
    return "; ".join(parts) if parts else "no strong individual drivers"


def build_patient(desynpuf_id: str) -> Patient:
    return Patient(
        id=desynpuf_id,
        identifier=[
            Identifier(
                system="https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files",
                value=desynpuf_id,
            )
        ],
        text={
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{SYNTHETIC_DATA_DISCLAIMER}</div>',
        },
    )


def build_risk_assessment(member_row, rationale: str) -> RiskAssessment:
    desynpuf_id = member_row["desynpuf_id"]
    return RiskAssessment(
        id=f"riskassessment-{desynpuf_id}",
        status="final",
        subject=Reference(reference=f"Patient/{desynpuf_id}"),
        occurrenceDateTime="2010-01-01T00:00:00Z",
        code=CodeableConcept(text="Predicted high-cost Medicare risk, 2010 calendar year"),
        method=CodeableConcept(
            text="XGBoost gradient-boosted tree classifier trained on 2008-2009 Medicare claims "
            "(admits, visits, spend, chronic conditions, demographics, Rx utilization)"
        ),
        prediction=[
            RiskAssessmentPrediction(
                outcome=CodeableConcept(text="High-cost (top decile of 2010 Medicare spend)"),
                probabilityDecimal=round(float(member_row["risk_score"]), 4),
                qualitativeRisk=CodeableConcept(text=RISK_TIER_LABELS[member_row["risk_tier"]]),
                rationale=rationale,
            )
        ],
        note=[Annotation(text=SYNTHETIC_DATA_DISCLAIMER)],
    )


def main(sample: int | None) -> None:
    member_scores = pd.read_parquet(DATA_DIR / "member_risk_scores.parquet")
    shap_values = pd.read_parquet(DATA_DIR / "xgboost_high_cost_shap_values.parquet")

    if sample:
        member_scores = member_scores.sample(n=sample, random_state=42).reset_index(drop=True)

    shap_by_id = shap_values.set_index("desynpuf_id")

    patient_path = OUT_DIR / "Patient.ndjson"
    risk_path = OUT_DIR / "RiskAssessment.ndjson"

    n_written = 0
    n_errors = 0
    with open(patient_path, "w") as pf, open(risk_path, "w") as rf:
        for _, row in member_scores.iterrows():
            try:
                shap_row = shap_by_id.loc[row["desynpuf_id"]]
                rationale = top_drivers_text(shap_row)

                patient = build_patient(row["desynpuf_id"])
                risk_assessment = build_risk_assessment(row, rationale)

                pf.write(patient.model_dump_json(exclude_none=True) + "\n")
                rf.write(risk_assessment.model_dump_json(exclude_none=True) + "\n")
                n_written += 1
            except Exception as e:
                n_errors += 1
                print(f"  error on {row['desynpuf_id']}: {e}")

    print(f"wrote {n_written:,} Patient + RiskAssessment resource pairs")
    print(f"  {patient_path}")
    print(f"  {risk_path}")
    if n_errors:
        print(f"  {n_errors} rows failed validation -- see errors above")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None, help="export only N members (for a quick test run)")
    args = parser.parse_args()
    main(args.sample)
