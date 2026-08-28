-- Cohort: Medicare beneficiaries continuously enrolled (Part A + B, no HMO)
-- in EVERY year of the study (2008, 2009, 2010), alive through the end of
-- the label window.
--
-- Beneficiary Summary is one row per beneficiary PER YEAR, so "continuously
-- enrolled" has to be checked against all three yearly tables -- checking
-- just one year's file would miss someone who, say, joined an HMO plan only
-- in 2009.
--
-- Run against interim tables loaded by src/etl (see notebooks/01_etl_load_raw.ipynb),
-- registered as beneficiary_summary_2008 / _2009 / _2010.

select
    b08.desynpuf_id,
    b10.bene_birth_dt,
    b10.bene_death_dt,
    b10.bene_sex_ident_cd,
    b10.bene_race_cd,
    b10.sp_state_code
from beneficiary_summary_2008 b08
join beneficiary_summary_2009 b09 on b08.desynpuf_id = b09.desynpuf_id
join beneficiary_summary_2010 b10 on b08.desynpuf_id = b10.desynpuf_id
where
    -- full-year Part A (HI) + Part B (SMI) coverage, no HMO/Medicare
    -- Advantage months, in every year -- HMO claims aren't reliably in this
    -- data, so any HMO month makes utilization look artificially low
    b08.bene_hi_cvrage_tot_mons = 12 and b08.bene_smi_cvrage_tot_mons = 12 and b08.bene_hmo_cvrage_tot_mons = 0
    and b09.bene_hi_cvrage_tot_mons = 12 and b09.bene_smi_cvrage_tot_mons = 12 and b09.bene_hmo_cvrage_tot_mons = 0
    and b10.bene_hi_cvrage_tot_mons = 12 and b10.bene_smi_cvrage_tot_mons = 12 and b10.bene_hmo_cvrage_tot_mons = 0
    -- alive through the end of the label window (2010's file is the most
    -- current death record)
    and (b10.bene_death_dt is null or b10.bene_death_dt > :label_window_end);
