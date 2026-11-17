/** Shared API types for the Phase 2A lifecycle workspace. */

export type ProposalStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "approved"
  | "in_progress"
  | "completed"
  | "rejected"
  | "withdrawn"
  | "cancelled"
  | "failed";

export type TransactionStatus =
  | "created"
  | "in_progress"
  | "transferred"
  | "verified"
  | "rejected"
  | "cancelled"
  | "failed";

export type Transition = {
  id: string;
  action: string;
  from_state: string;
  to_state: string;
  actor_id: string;
  actor_role: string;
  organization_id: string | null;
  reason: string | null;
  context: Record<string, unknown>;
  occurred_at: string;
};

export type TransactionSummary = {
  id: string;
  proposal_id: string;
  status: TransactionStatus;
  accepted_quantity: number | null;
  transferred_quantity: number | null;
  verified_quantity: number | null;
  unit: string;
  carrier_name: string | null;
  transport_distance_km: number | null;
  transfer_reference: string | null;
  material_identification: string | null;
  transferred_at: string | null;
  verified_at: string | null;
  verification_method: string | null;
  source_organization_id: string;
  destination_organization_id: string;
  source_organization_name: string | null;
  destination_organization_name: string | null;
  material_name: string | null;
  material_reference: string | null;
  is_demo: boolean;
  version: number;
  created_at: string;
  available_actions: string[];
};

export type TransactionDetail = TransactionSummary & {
  evidence: Record<string, unknown>;
  notes: string | null;
  transfer_recorded_by: string | null;
  verified_by: string | null;
  rejection_reason: string | null;
  cancelled_by: string | null;
  cancellation_reason: string | null;
  history: Transition[];
};

export type ProposalSummary = {
  id: string;
  status: ProposalStatus;
  quantity: number;
  unit: string;
  price_per_unit: number | null;
  currency: string;
  compatibility_status: string;
  version: number;
  is_demo: boolean;
  opportunity_id: string;
  proposed_by_organization_id: string;
  receiving_organization_id: string;
  material_name: string | null;
  material_reference: string | null;
  supplier_name: string | null;
  consumer_name: string | null;
  transaction_id: string | null;
  transaction_status: string | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  completed_at: string | null;
  available_actions: string[];
};

export type ProposalDetail = ProposalSummary & {
  terms: Record<string, unknown>;
  valid_until: string | null;
  notes: string | null;
  submitted_by: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approval_reference: string | null;
  approval_evidence: Record<string, unknown>;
  rejected_by: string | null;
  rejection_reason: string | null;
  withdrawn_by: string | null;
  withdrawn_at: string | null;
  started_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  failed_at: string | null;
  failure_reason: string | null;
  transaction: TransactionDetail | null;
  history: Transition[];
};

export type AuditRecord = {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  previous_state: string | null;
  new_state: string | null;
  actor: string;
  actor_id: string | null;
  organization_id: string | null;
  severity: string;
  summary: string;
  reason: string | null;
  detail: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type Actor = {
  actor_id: string;
  display_name: string;
  role: string;
  organization_id?: string | null;
  organization_slug?: string | null;
  organization_name?: string | null;
  is_development: boolean;
};

export const PROPOSAL_ACTION_LABELS: Record<string, string> = {
  submit: "Submit for review",
  review: "Start review",
  approve: "Approve",
  reject: "Reject",
  withdraw: "Withdraw",
};

export const TRANSACTION_ACTION_LABELS: Record<string, string> = {
  record_transfer: "Record transfer",
  verify: "Verify quantity",
  reject: "Reject",
  cancel: "Cancel",
};

export const TERMINAL_PROPOSAL_STATES: ProposalStatus[] = [
  "completed",
  "rejected",
  "withdrawn",
  "cancelled",
  "failed",
];
