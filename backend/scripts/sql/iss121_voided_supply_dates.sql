-- ISS-121: complaints whose supply date may come from a voided dispatch.
-- Before 053 the complaint form prefilled the challan and supply date from the
-- order's latest dispatch, voided or not. Lists each complaint whose challan
-- number belongs only to voided dispatches of its order, for staff to review.
-- Read only. Run as the owner role (no RLS), once per environment.
SELECT c.complaint_no, c.status, c.dc_no, c.supply_date,
       o.order_no, d.voided_at
  FROM complaint c
  JOIN sales_order o ON o.id = c.sales_order_id
  JOIN dispatch d ON d.sales_order_id = c.sales_order_id AND d.dc_no = c.dc_no
 WHERE c.deleted_at IS NULL
   AND d.voided_at IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dispatch live
                    WHERE live.sales_order_id = c.sales_order_id
                      AND live.dc_no = c.dc_no AND live.voided_at IS NULL)
 ORDER BY c.complaint_no;
