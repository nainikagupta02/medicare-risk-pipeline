-- Amount paid by a primary payer OTHER than Medicare (e.g. employer
-- retiree coverage, other insurance), summed across both feature-window
-- years (2008 + 2009). Only available as an annual beneficiary-level total,
-- not at the claim level, so it can't be date-filtered the way claims can.
--
-- Useful signal on its own: someone with substantial other-payer coverage
-- may show artificially low Medicare-paid amounts in the utilization
-- features even though their total care utilization is high.

select
    c.desynpuf_id,
    coalesce(b08.pppymt_ip, 0) + coalesce(b08.pppymt_op, 0) + coalesce(b08.pppymt_car, 0)
    + coalesce(b09.pppymt_ip, 0) + coalesce(b09.pppymt_op, 0) + coalesce(b09.pppymt_car, 0)
    as other_payer_paid
from continuously_enrolled c
join beneficiary_summary_2008 b08 on c.desynpuf_id = b08.desynpuf_id
join beneficiary_summary_2009 b09 on c.desynpuf_id = b09.desynpuf_id;
