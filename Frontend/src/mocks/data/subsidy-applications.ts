/**
 * SUBS-006, SUBS-007 · The mock's subsidy stages and document checklist, as the backend seeds
 * them (migration `025_subsidy_applications`). The stages are data on the backend too: the
 * screens build their forms from `GET /subsidy-stages`, never from this list.
 */

export interface MockStageField {
  readonly key: string;
  readonly label: string;
  readonly type: "date" | "amount" | "text";
  /** A stage-16 amount's stage-17 received date: all of them in closes the application. */
  readonly pairsWith?: string;
}

export interface MockStageDef {
  readonly seq: number;
  readonly code: string;
  readonly name: string;
  readonly fields: readonly MockStageField[];
}

export const MOCK_STAGE_DEFS: readonly MockStageDef[] = [
  {
    seq: 4,
    code: "application_in_process",
    name: "Application in process",
    fields: [
      { key: "app_inward", label: "App. Inward Date", type: "date" },
      { key: "app_re_inward", label: "App. Re-Inward Date", type: "date" },
      { key: "apply_date", label: "Apply Date", type: "date" },
      { key: "reg_no", label: "Reg. No.", type: "text" },
      { key: "doc_check", label: "App. Document Check Date", type: "date" },
      { key: "app_query", label: "App Query Date", type: "date" },
      { key: "app_query_solved", label: "App Query Solve Date", type: "date" },
      { key: "return_to_field", label: "Return to Field Date", type: "date" },
    ],
  },
  {
    seq: 5,
    code: "technical_in_process",
    name: "Technical in process",
    fields: [
      { key: "tech_received", label: "Tech. Received Date", type: "date" },
      { key: "tech_check", label: "Tech Check Date", type: "date" },
      { key: "tech_query", label: "Tech Query Date", type: "date" },
      { key: "tech_query_solved", label: "Tech Query Solve Date", type: "date" },
      { key: "tech_return_to_field", label: "Return to Field Date", type: "date" },
    ],
  },
  {
    seq: 6,
    code: "submitted_wo_pending",
    name: "Application submitted, WO pending",
    fields: [{ key: "submission", label: "App. Submission Date", type: "date" }],
  },
  {
    seq: 7,
    code: "farmer_share",
    name: "Farmer share detail",
    fields: [
      { key: "farmer_share_amt", label: "Farmer Share Amt.", type: "amount" },
      { key: "fs_credited_1", label: "FS Credited Date-1", type: "date" },
      { key: "fs_credited_2", label: "FS Credited Date-2", type: "date" },
      { key: "supply", label: "Original Material Supply Date", type: "date" },
    ],
  },
  {
    seq: 8,
    code: "ggrc_query",
    name: "GGRC query",
    fields: [
      { key: "query_1", label: "Query-1 Date", type: "date" },
      { key: "query_1_solved", label: "Query-1 Solve Date", type: "date" },
      { key: "query_2", label: "Query-2 Date", type: "date" },
      { key: "query_2_solved", label: "Query-2 Solve Date", type: "date" },
      { key: "query_3", label: "Query-3 Date", type: "date" },
      { key: "query_3_solved", label: "Query-3 Solve Date", type: "date" },
    ],
  },
  {
    seq: 9,
    code: "wo_issued",
    name: "WO issued, TPA pending",
    fields: [{ key: "wo_received", label: "WO Received Date", type: "date" }],
  },
  {
    seq: 10,
    code: "tpa_sent",
    name: "TPA sent",
    fields: [
      { key: "tpa_received", label: "TPA Received Date", type: "date" },
      { key: "tpa_date", label: "TPA Date", type: "date" },
      { key: "tpa_sent", label: "TPA Sent Date", type: "date" },
    ],
  },
  {
    seq: 11,
    code: "inspection_call_pending",
    name: "Inspection call pending",
    fields: [{ key: "tpa_cleared", label: "TPA Cleared Date", type: "date" }],
  },
  {
    seq: 12,
    code: "tr_pending",
    name: "TR pending",
    fields: [
      { key: "inspection_sent", label: "Inspection Sent Date", type: "date" },
      { key: "tpia_name", label: "TPIA Name", type: "text" },
      { key: "tr_planning_1", label: "TR Planning Date-1", type: "date" },
      { key: "tr_planning_2", label: "TR Planning Date-2", type: "date" },
      { key: "tr_not_ok", label: "TR Not Ok Date", type: "date" },
      { key: "tr_not_ok_remark", label: "TR Not Ok Remark", type: "text" },
    ],
  },
  {
    seq: 13,
    code: "tr_done",
    name: "TR done",
    fields: [
      { key: "tr_received", label: "TR Received Date", type: "date" },
      { key: "tr_date", label: "TR Date", type: "date" },
    ],
  },
  {
    seq: 14,
    code: "fp_invoice_submitted",
    name: "FP invoice submitted",
    fields: [
      { key: "fp_amount", label: "FP Amount", type: "amount" },
      { key: "deduction_amount", label: "Deduction Amount", type: "amount" },
      { key: "fp_submitted", label: "FP Invoice Submitted Date", type: "date" },
    ],
  },
  {
    seq: 15,
    code: "fp_query",
    name: "FP query",
    fields: [
      { key: "fp_query_remark", label: "FP Query Remark", type: "text" },
      { key: "fp_query_received", label: "FP Query Received Date", type: "date" },
      { key: "fp_query_solved", label: "FP Query Solve Date", type: "date" },
    ],
  },
  {
    seq: 16,
    code: "fp_cleared_pay_pending",
    name: "FP cleared, payment pending",
    fields: [
      { key: "fp_cleared", label: "FP Cleared Date", type: "date" },
      { key: "pfms_amt", label: "PFMS/Central Amt.", type: "amount", pairsWith: "pfms_received" },
      {
        key: "state_share_amt",
        label: "State Share Amt.",
        type: "amount",
        pairsWith: "state_share_received",
      },
      {
        key: "fp_farmer_share_amt",
        label: "Farmer Share Amt.",
        type: "amount",
        pairsWith: "farmer_share_received",
      },
      {
        key: "fp_deduction_amt",
        label: "Deduction Amt.",
        type: "amount",
        pairsWith: "deduction_recovered",
      },
      {
        key: "retention_amt",
        label: "Retention Amt.",
        type: "amount",
        pairsWith: "retention_received",
      },
      {
        key: "dept_hold_amt",
        label: "Dept. Hold Amt.",
        type: "amount",
        pairsWith: "dept_hold_received",
      },
      { key: "total_fp_amt", label: "Total FP Amount", type: "amount" },
    ],
  },
  {
    seq: 17,
    code: "payment_received",
    name: "Payment received",
    fields: [
      { key: "pfms_received", label: "PFMS/Central Amt. Date", type: "date" },
      { key: "state_share_received", label: "State Share Amt. Date", type: "date" },
      { key: "farmer_share_received", label: "Farmer Share Amt. Date", type: "date" },
      { key: "deduction_recovered", label: "Deduction Amt. Recovery Date", type: "date" },
      { key: "retention_received", label: "Retention Amt. Rec. Date", type: "date" },
      { key: "dept_hold_received", label: "Dept. Hold Amt. Date", type: "date" },
    ],
  },
];

export const MOCK_DOCUMENT_TYPES: readonly { code: string; name: string }[] = [
  { code: "farmer_application_form_1", name: "Farmer Application (Form-1)" },
  { code: "8a_7_12", name: "8 A & 7/12" },
  { code: "form_16", name: "Form No. 16" },
  { code: "bank_sanction_letter", name: "Bank Sanction Letter" },
  { code: "farmer_type_certificate", name: "Type of Farmer Certificate" },
  { code: "caste_certificate", name: "Caste certificate" },
  { code: "affidavit_8a", name: "Affidavit by Farmer for Form No. 8A" },
  {
    code: "joint_owner_undertaking",
    name: "Undertaking (Rs 20 stamp paper) from other joint owners on 7-12",
  },
  { code: "water_sharing_agreement", name: "Water sharing Agreement on Rs 20 stamp paper" },
  { code: "photo_identity", name: "Attested photo identity card" },
  { code: "irrigation_data", name: "Irrigation Data" },
  { code: "form_6", name: "Form No. 6" },
  { code: "quotation_summary", name: "Quotation Summary (A+B+C)" },
  { code: "quotation_a", name: "Quotation A (head and field unit, with transportation)" },
  { code: "quotation_b", name: "Quotation B (agronomy consultancy)" },
  { code: "quotation_c", name: "Quotation C (installation)" },
  { code: "consent_letter", name: "Farmer's consent letter (Sammati Patrak)" },
  { code: "design", name: "Design" },
  { code: "soil_water_report", name: "Soil & Water Analysis Report" },
  { code: "techno_economic_report", name: "Techno Economic Report" },
];
