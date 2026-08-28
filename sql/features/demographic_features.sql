-- Demographics as of the end of the feature window (2009-12-31): age, sex,
-- and race. Computed only for cohort members.

select
    c.desynpuf_id,
    -- dates in this file are plain YYYYMMDD integers (e.g. 19230501), not a
    -- date type, so age is derived from the birth year digits directly
    2009 - cast(substr(cast(b.bene_birth_dt as varchar), 1, 4) as integer) as age,
    (b.bene_sex_ident_cd = 1)::int as is_male,
    (b.bene_race_cd = 2)::int as race_black,
    (b.bene_race_cd = 3)::int as race_other,
    (b.bene_race_cd = 5)::int as race_hispanic
    -- race_white is the implicit baseline (bene_race_cd = 1) and is left out
    -- to avoid the one-hot dummy trap
from continuously_enrolled c
join beneficiary_summary_2009 b on c.desynpuf_id = b.desynpuf_id;
