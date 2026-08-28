"""Demonstrate a real FHIR round-trip: PUT a handful of the exported
Patient + RiskAssessment resources to a public FHIR R4 test server, then GET
them back to confirm the server actually accepted and persisted them.

hapi.fhir.org is a well-known public sandbox maintained specifically for
this kind of testing -- no credentials needed, and it's routinely wiped, so
nothing posted here is meant to persist. Only ever run this against a public
TEST server with synthetic data (which is all this project ever produces) --
never against a real FHIR endpoint holding real patient data.

Usage:
    python fhir/post_to_test_server.py [--n 5]
"""

import argparse
import json
from pathlib import Path

import requests

BASE_URL = "https://hapi.fhir.org/baseR4"
OUT_DIR = Path(__file__).resolve().parent / "output"


def _with_retry(request_fn, attempts=3):
    last_error = None
    for _ in range(attempts):
        try:
            return request_fn()
        except requests.exceptions.RequestException as e:
            last_error = e
    raise last_error


def put_resource(resource: dict) -> requests.Response:
    resource_type = resource["resourceType"]
    resource_id = resource["id"]
    url = f"{BASE_URL}/{resource_type}/{resource_id}"
    return _with_retry(lambda: requests.put(
        url, json=resource, headers={"Content-Type": "application/fhir+json"}, timeout=30
    ))


def get_resource(resource_type: str, resource_id: str) -> requests.Response:
    url = f"{BASE_URL}/{resource_type}/{resource_id}"
    return _with_retry(lambda: requests.get(
        url, headers={"Accept": "application/fhir+json"}, timeout=30
    ))


def main(n: int) -> None:
    with open(OUT_DIR / "Patient.ndjson") as f:
        patients = [json.loads(next(f)) for _ in range(n)]
    with open(OUT_DIR / "RiskAssessment.ndjson") as f:
        risk_assessments = [json.loads(next(f)) for _ in range(n)]

    print(f"POSTing {n} Patient + RiskAssessment pairs to {BASE_URL} ...\n")

    for patient, risk_assessment in zip(patients, risk_assessments):
        patient_resp = put_resource(patient)
        print(f"  PUT Patient/{patient['id']} -> {patient_resp.status_code}")

        ra_resp = put_resource(risk_assessment)
        print(f"  PUT RiskAssessment/{risk_assessment['id']} -> {ra_resp.status_code}")

    print("\nfetching them back to confirm persistence ...\n")

    for patient, risk_assessment in zip(patients, risk_assessments):
        get_resp = get_resource("RiskAssessment", risk_assessment["id"])
        if get_resp.status_code == 200:
            fetched = get_resp.json()
            probability = fetched["prediction"][0]["probabilityDecimal"]
            rationale = fetched["prediction"][0]["rationale"]
            print(f"  GET RiskAssessment/{risk_assessment['id']} -> 200 "
                  f"(probability={probability}, rationale=\"{rationale[:60]}...\")")
        else:
            print(f"  GET RiskAssessment/{risk_assessment['id']} -> {get_resp.status_code} (unexpected)")

    print(f"\nview these live at: {BASE_URL}/RiskAssessment/{risk_assessments[0]['id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5, help="number of resource pairs to POST")
    args = parser.parse_args()
    main(args.n)
