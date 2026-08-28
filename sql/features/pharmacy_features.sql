-- Prescription drug utilization and spend over a given window (feature
-- window when building predictors, label window when scoring 2010 drug
-- spend). Bind :window_start / :window_end before running.

select
    c.desynpuf_id,
    count(distinct p.pde_id) as rx_fill_count,
    coalesce(sum(p.tot_rx_cst_amt), 0) as rx_total_cost,
    coalesce(sum(p.ptnt_pay_amt), 0) as rx_patient_paid
from continuously_enrolled c
left join prescription_drug_events p
    on c.desynpuf_id = p.desynpuf_id
    and p.srvc_dt between :window_start and :window_end
group by c.desynpuf_id;
