/**
 * Platform-console DTOs.
 *
 * These mirror `app/schemas/platform.py` exactly and are deliberately separate
 * from the organisation-workspace types: the console never receives tenant
 * business records, so its types cannot grow a field for them by accident.
 */

export type OrganizationStatus = "active" | "suspended";

export type PlatformOrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  sector: string;
  country: string;
  city: string | null;
  status: OrganizationStatus;
  is_demo: boolean;
  created_at: string;
  suspended_at: string | null;
};

export type PlatformOrganizationRow = PlatformOrganizationSummary & {
  active_members: number;
  suspended_members: number;
  pending_invitations: number;
};

export type PlatformMembershipCounts = {
  active: number;
  suspended: number;
  invited: number;
  removed: number;
};

export type PlatformInvitationCounts = {
  pending: number;
  expired: number;
  accepted: number;
  revoked: number;
};

export type PlatformAuditSummary = {
  id: string;
  created_at: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  actor: string;
  severity: string;
  summary: string;
  organization_id: string | null;
  organization_name: string | null;
};

export type PlatformOrganizationDetail = PlatformOrganizationSummary & {
  members: PlatformMembershipCounts;
  invitations: PlatformInvitationCounts;
  administrators: Record<string, number>;
  last_activity_at: string | null;
  state: string;
  warnings: string[];
  checks: string[];
  recent_events: PlatformAuditSummary[];
};

export type PlatformDashboard = {
  generated_at: string;
  window_days: number;
  failure_window_hours: number;
  organisations: {
    total: number;
    active: number;
    suspended: number;
    created_in_window: number;
  };
  users: { total: number; active: number };
  memberships: PlatformMembershipCounts;
  pending_invitations: number;
  failed_logins_window: number;
  recent_organisations: PlatformOrganizationSummary[];
  recent_events: PlatformAuditSummary[];
};

export type PlatformTenantHealth = {
  organization: PlatformOrganizationSummary;
  active_members: number;
  suspended_members: number;
  pending_invitations: number;
  active_administrators: number;
  admin_changes_window: number;
  security_events_window: number;
  member_auth_failures_window: number;
  last_activity_at: string | null;
  state: string;
  warnings: string[];
  checks: string[];
};

export type ApprovalAction = "suspend" | "reactivate";
export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "cancelled"
  | "expired"
  | "executed";

export type PlatformApproval = {
  id: string;
  organization_id: string;
  organization_name: string | null;
  organization_slug: string | null;
  organization_status: OrganizationStatus | null;
  action: ApprovalAction;
  reason: string | null;
  status: ApprovalStatus;
  requested_by_user_id: string;
  requested_by: string | null;
  created_at: string;
  expires_at: string;
  decided_by_user_id: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_reason: string | null;
  executed_by_user_id: string | null;
  executed_by: string | null;
  executed_at: string | null;
  is_expired: boolean;
  can_decide: boolean;
  can_execute: boolean;
  can_cancel: boolean;
};

export type PlatformOperatorSession = {
  id: string;
  user_id: string;
  user_email: string;
  created_at: string;
  last_seen_at: string | null;
  mfa_verified_at: string | null;
  revoked_at: string | null;
  revoked_reason: string | null;
  is_current: boolean;
  user_agent: string | null;
};

export type MfaStatus = {
  enrolled: boolean;
  verified: boolean;
  required: boolean;
  enrollment_required: boolean;
  recovery_codes_remaining: number;
  locked_until: string | null;
  method: string | null;
};

export type MfaEnrollment = {
  secret: string;
  provisioning_uri: string;
  message: string;
};

export type MfaConfirmation = {
  message: string;
  recovery_codes: string[];
  enrolled_at: string;
};

export type PlatformAuditEvent = {
  id: string;
  created_at: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  actor: string;
  actor_id: string | null;
  organization_id: string | null;
  organization_name: string | null;
  severity: string;
  summary: string;
  reason: string | null;
  previous_state: string | null;
  new_state: string | null;
  payload: Record<string, unknown>;
  redacted_fields: string[];
};
