-- Cohort-level monthly spend + utilization, 2008-01 through 2010-12 (36
-- months). Aggregated at the cohort level, not per member -- a per-member
-- monthly series would be too sparse to forecast (most members don't have a
-- claim every month), so this is the total across all 52,375 cohort members
-- for each calendar month.
--
-- Each claim type is aggregated to one row per month BEFORE joining, same
-- reasoning as utilization_features.sql: joining three raw claims tables
-- directly would fan out and multiply the sums.
--
-- clm_from_dt is a YYYYMMDD value, so integer-dividing by 100 truncates the
-- day and leaves YYYYMM directly (e.g. 20100312 // 100 = 201003). it's read
-- back as a float in inpatient/outpatient (a small number of rows have a
-- null clm_from_dt, which forces the whole column to float64), so it's
-- explicitly cast to bigint first -- // on a double does true division, not
-- floor division, which would otherwise produce a fractional "month" like
-- 201003.12 instead of 201003.
--
-- rows are also restricted to clm_from_dt is not null and within the
-- 2008-01 to 2010-12 study period -- a small number of claims (mostly
-- inpatient stays admitted before the file's official start) fall outside
-- it and would otherwise create a handful of stray months in the series.

with inpatient_monthly as (
    select
        cast(i.clm_from_dt as bigint) // 100 as year_month,
        count(distinct i.clm_id) as inpatient_admits,
        sum(coalesce(i.clm_pmt_amt, 0)) as inpatient_paid
    from inpatient_claims i
    join continuously_enrolled c on i.desynpuf_id = c.desynpuf_id
    where i.clm_from_dt is not null
      and i.clm_from_dt between 20080101 and 20101231
    group by year_month
),
outpatient_monthly as (
    select
        cast(o.clm_from_dt as bigint) // 100 as year_month,
        count(distinct o.clm_id) as outpatient_visits,
        sum(coalesce(o.clm_pmt_amt, 0)) as outpatient_paid
    from outpatient_claims o
    join continuously_enrolled c on o.desynpuf_id = c.desynpuf_id
    where o.clm_from_dt is not null
      and o.clm_from_dt between 20080101 and 20101231
    group by year_month
),
carrier_monthly as (
    select
        cast(car.clm_from_dt as bigint) // 100 as year_month,
        count(distinct car.clm_id) as carrier_claims,
        sum(
            coalesce(car.line_nch_pmt_amt_1, 0) + coalesce(car.line_nch_pmt_amt_2, 0)
            + coalesce(car.line_nch_pmt_amt_3, 0) + coalesce(car.line_nch_pmt_amt_4, 0)
            + coalesce(car.line_nch_pmt_amt_5, 0) + coalesce(car.line_nch_pmt_amt_6, 0)
            + coalesce(car.line_nch_pmt_amt_7, 0) + coalesce(car.line_nch_pmt_amt_8, 0)
            + coalesce(car.line_nch_pmt_amt_9, 0) + coalesce(car.line_nch_pmt_amt_10, 0)
            + coalesce(car.line_nch_pmt_amt_11, 0) + coalesce(car.line_nch_pmt_amt_12, 0)
            + coalesce(car.line_nch_pmt_amt_13, 0)
        ) as carrier_paid
    from carrier_claims car
    join continuously_enrolled c on car.desynpuf_id = c.desynpuf_id
    where car.clm_from_dt is not null
      and car.clm_from_dt between 20080101 and 20101231
    group by year_month
)
select
    coalesce(i.year_month, o.year_month, car.year_month) as year_month,
    coalesce(i.inpatient_admits, 0) as inpatient_admits,
    coalesce(o.outpatient_visits, 0) as outpatient_visits,
    coalesce(car.carrier_claims, 0) as carrier_claims,
    coalesce(i.inpatient_paid, 0) + coalesce(o.outpatient_paid, 0) + coalesce(car.carrier_paid, 0) as total_paid
from inpatient_monthly i
full outer join outpatient_monthly o on i.year_month = o.year_month
full outer join carrier_monthly car on coalesce(i.year_month, o.year_month) = car.year_month
order by year_month;
