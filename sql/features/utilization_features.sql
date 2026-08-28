-- Per-member utilization + spend, computed over a given window. Bind
-- :window_start / :window_end before running -- use the feature window
-- (2008-2009) to build predictors, or the label window (2010) to derive the
-- high_utilization / high_cost labels.
--
-- Each claim type is aggregated to one row per member BEFORE joining --
-- joining three raw claims tables directly on desynpuf_id would fan out
-- (a member with 5 inpatient claims and 100 carrier claims would produce
-- 500 joined rows, multiplying every sum by the wrong factor).

with inpatient_agg as (
    select
        desynpuf_id,
        count(distinct clm_id) as inpatient_admits,
        sum(coalesce(clm_pmt_amt, 0)) as inpatient_paid
    from inpatient_claims
    where clm_from_dt between :window_start and :window_end
    group by desynpuf_id
),
outpatient_agg as (
    select
        desynpuf_id,
        count(distinct clm_id) as outpatient_visits,
        sum(coalesce(clm_pmt_amt, 0)) as outpatient_paid
    from outpatient_claims
    where clm_from_dt between :window_start and :window_end
    group by desynpuf_id
),
carrier_agg as (
    -- carrier claims are line-level: up to 13 service lines per claim, each
    -- with its own payment amount, so the line amounts are added together
    -- per claim row before summing across claims
    select
        desynpuf_id,
        count(distinct clm_id) as carrier_claims,
        sum(
            coalesce(line_nch_pmt_amt_1, 0) + coalesce(line_nch_pmt_amt_2, 0)
            + coalesce(line_nch_pmt_amt_3, 0) + coalesce(line_nch_pmt_amt_4, 0)
            + coalesce(line_nch_pmt_amt_5, 0) + coalesce(line_nch_pmt_amt_6, 0)
            + coalesce(line_nch_pmt_amt_7, 0) + coalesce(line_nch_pmt_amt_8, 0)
            + coalesce(line_nch_pmt_amt_9, 0) + coalesce(line_nch_pmt_amt_10, 0)
            + coalesce(line_nch_pmt_amt_11, 0) + coalesce(line_nch_pmt_amt_12, 0)
            + coalesce(line_nch_pmt_amt_13, 0)
        ) as carrier_paid
    from carrier_claims
    where clm_from_dt between :window_start and :window_end
    group by desynpuf_id
)
select
    b.desynpuf_id,
    coalesce(ip.inpatient_admits, 0) as inpatient_admits,
    coalesce(op.outpatient_visits, 0) as outpatient_visits,
    coalesce(car.carrier_claims, 0) as carrier_claims,
    coalesce(ip.inpatient_paid, 0) as inpatient_paid,
    coalesce(op.outpatient_paid, 0) as outpatient_paid,
    coalesce(car.carrier_paid, 0) as carrier_paid
from continuously_enrolled b
left join inpatient_agg ip on b.desynpuf_id = ip.desynpuf_id
left join outpatient_agg op on b.desynpuf_id = op.desynpuf_id
left join carrier_agg car on b.desynpuf_id = car.desynpuf_id;
