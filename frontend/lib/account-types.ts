/**
 * Onboarding and account-security payloads.
 *
 * These mirror the API's read models. Nothing here is trusted: the backend
 * re-checks permissions, tenant scope and the password policy on every call.
 */

export type InvitationStatus = "pending" | "accepted" | "revoked" | "expired";

export type Invitation = {
  id: string;
  email: string;
  organization_id: string;
  organization_name: string | null;
  role: string;
  scope: string;
  status: InvitationStatus | string;
  expires_at: string;
  created_at: string;
  invited_by_user_id: string | null;
  accepted_at: string | null;
  note: string | null;
  /** Development delivery only; the API omits it everywhere else. */
  delivery_token: string | null;
};

/** One organisation membership as exposed to a member administrator. */
export type Member = {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  scope: string;
  status: string;
  joined_at: string | null;
  is_self: boolean;
};

export type MemberAction = { member: Member; sessions_revoked: number };

export type MemberResetResult = MemberAction & {
  must_change_password: boolean;
  message: string;
};

/** Every role in the membership catalogue, most privileged by administration first. */
export const MEMBER_ROLE_VALUES = [
  "org_admin",
  "coordinator",
  "reviewer",
  "approver",
  "auditor",
  "viewer",
] as const;

export const MEMBER_STATUS_LABELS: Record<string, string> = {
  invited: "Invited",
  active: "Active",
  suspended: "Deactivated",
  removed: "Removed",
};

export function membershipStatusLabel(status: string): string {
  return MEMBER_STATUS_LABELS[status] ?? status;
}

export function scopeLabel(scope: string): string {
  return scope === "platform" ? "Platform-wide" : "Organisation";
}

export type SessionInfo = {
  id: string;
  organization_id: string | null;
  created_at: string;
  last_seen_at: string | null;
  access_expires_at: string;
  refresh_expires_at: string;
  revoked_at: string | null;
  revoked_reason: string | null;
  is_current: boolean;
  user_agent: string | null;
};

export const INVITATION_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  accepted: "Accepted",
  revoked: "Revoked",
  expired: "Expired",
};

export function invitationStatusLabel(status: string): string {
  return INVITATION_STATUS_LABELS[status] ?? status;
}

/** Roles a member administrator may offer. Server-side scope checks still win. */
export const INVITABLE_ROLES: { value: string; label: string; needsMemberManage: boolean }[] = [
  { value: "coordinator", label: "Coordinator — proposes and records activity", needsMemberManage: false },
  { value: "reviewer", label: "Reviewer — assesses proposals", needsMemberManage: false },
  { value: "approver", label: "Approver — authorises transactions", needsMemberManage: false },
  { value: "auditor", label: "Auditor — verifies evidence", needsMemberManage: false },
  { value: "viewer", label: "Viewer — read-only access", needsMemberManage: false },
  { value: "org_admin", label: "Organisation admin — manages members", needsMemberManage: true },
];

export function invitableRoles(permissions: string[]) {
  return INVITABLE_ROLES.filter(
    (role) => !role.needsMemberManage || permissions.includes("member.manage"),
  );
}

/** A short, non-identifying description of the client that opened a session. */
export function deviceLabel(userAgent: string | null | undefined): string {
  if (!userAgent) return "Unknown device";
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /OPR\//.test(userAgent)
      ? "Opera"
      : /Chrome\//.test(userAgent)
        ? "Chrome"
        : /Firefox\//.test(userAgent)
          ? "Firefox"
          : /Safari\//.test(userAgent)
            ? "Safari"
            : "Browser";
  const platform = /Windows/.test(userAgent)
    ? "Windows"
    : /Android/.test(userAgent)
      ? "Android"
      : /iPhone|iPad|iPod/.test(userAgent)
        ? "iOS"
        : /Mac OS X/.test(userAgent)
          ? "macOS"
          : /Linux/.test(userAgent)
            ? "Linux"
            : null;
  return platform ? `${browser} on ${platform}` : browser;
}

/** Whether an invitation's expiry has already passed, in the viewer's clock. */
export function isExpired(expiresAt: string): boolean {
  const date = new Date(expiresAt);
  return !Number.isNaN(date.getTime()) && date.getTime() <= Date.now();
}
