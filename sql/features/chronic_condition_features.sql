-- Chronic condition flags as of the most recent feature-window year (2009),
-- computed only from cohort members so counts line up with the feature
-- table. 1 = has condition, 2 = does not, per the CMS DE-SynPUF coding.

select
    c.desynpuf_id,
    (b.sp_alzhdmta = 1)::int as has_alzheimers,
    (b.sp_chf = 1)::int      as has_chf,
    (b.sp_chrnkidn = 1)::int as has_ckd,
    (b.sp_cncr = 1)::int     as has_cancer,
    (b.sp_copd = 1)::int     as has_copd,
    (b.sp_depressn = 1)::int as has_depression,
    (b.sp_diabetes = 1)::int as has_diabetes,
    (b.sp_ischmcht = 1)::int as has_ihd,
    (b.sp_osteoprs = 1)::int as has_osteoporosis,
    (b.sp_ra_oa = 1)::int    as has_ra_oa,
    (b.sp_strketia = 1)::int as has_stroke_tia,
    -- end-stage renal disease is coded 'Y'/'0' (string), not 1/2 like the
    -- sp_* flags -- one of the strongest real-world Medicare cost drivers,
    -- so worth including even though it's a small share of the cohort
    (b.bene_esrd_ind = 'Y')::int as has_esrd
from continuously_enrolled c
join beneficiary_summary_2009 b on c.desynpuf_id = b.desynpuf_id;
