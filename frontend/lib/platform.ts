/**
 * Platform-console access rules, navigation and presentation helpers.
 *
 * Nothing here authorizes anything: the API checks `is_platform_admin` and the
 * platform capability on every request. These helpers only decide what the
 * console renders, so a hidden link can never be mistaken for a permission.
 */

import { hasPermission, type SessionUser } from "@/lib/auth";
import type { SessionState } from "@/lib/session";

export const PLATFORM_PERMISSION = {
  admin: "platform.admin",
  dashboard: "platform.dashboard.view",
  organizationsView: "platform.organizations.view",
  organizationsManage: "platform.organizations.manage",
  audit: "platform.audit.view",
  auditExport: "platform.audit.export",
  health: "platform.health.view",
  approvalsView: "platform.approvals.view",
  approvalsRequest: "platform.approvals.request",
  approvalsDecide: "platform.approvals.decide",
  approvalsExecute: "platform.approvals.execute",
  sessionsManage: "platform.sessions.manage",
} as const;

export type PlatformNavItem = {
  href: string;
  label: string;
  short: string;
  permission: string;
};

export const PLATFORM_NAV: PlatformNavItem[] = [
  {
    href: "/platform",
    label: "Operator overview",
    short: "Overview",
    permission: PLATFORM_PERMISSION.dashboard,
  },
  {
    href: "/platform/organizations",
    label: "Organisation register",
    short: "Organisations",
    permission: PLATFORM_PERMISSION.organizationsView,
  },
  {
    href: "/platform/health",
    label: "Tenant health",
    short: "Health",
    permission: PLATFORM_PERMISSION.health,
  },
  {
    href: "/platform/audit",
    label: "Audit journal",
    short: "Audit",
    permission: PLATFORM_PERMISSION.audit,
  },
  {
    href: "/platform/approvals",
    label: "Approvals",
    short: "Approvals",
    permission: PLATFORM_PERMISSION.approvalsView,
  },
  {
    href: "/platform/security",
    label: "Operator security",
    short: "Security",
    permission: PLATFORM_PERMISSION.admin,
  },
];

/**
 * Platform authority is the explicit account flag *and* the capability.
 *
 * A cross-tenant `scope=platform` membership grants reach inside the workspace;
 * it has never granted the console, and this check keeps that true in the UI as
 * well as in the API.
 */
export function isPlatformOperator(user: SessionUser | null | undefined): boolean {
  return Boolean(user?.is_platform_admin);
}

export function canPlatform(
  user: SessionUser | null | undefined,
  permission: string,
): boolean {
  return isPlatformOperator(user) && hasPermission(user ?? null, permission);
}

export type PlatformGate = "offline" | "signed_out" | "password" | "workspace" | "ok";

/**
 * Decide what the platform layout should do before it renders anything.
 *
 * A refusal returns `workspace` so the layout redirects on the server: an
 * organisation administrator who types `/platform` into the address bar never
 * receives console markup that could flash before a client-side redirect.
 */
export function platformGate(state: SessionState): PlatformGate {
  if (state.status === "unavailable") return "offline";
  if (state.status === "anonymous") return "signed_out";
  if (state.user.must_change_password) return "password";
  if (!isPlatformOperator(state.user)) return "workspace";
  return "ok";
}

export function platformNavFor(permissions: string[]): PlatformNavItem[] {
  return PLATFORM_NAV.filter((item) => permissions.includes(item.permission));
}

export function isPlatformActive(pathname: string, href: string): boolean {
  if (href === "/platform") return pathname === "/platform";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export type StatusTone = "forest" | "warning" | "danger" | "muted" | "outline";

export function platformStatusLabel(status: string): string {
  return status === "suspended" ? "Suspended" : status === "active" ? "Active" : status;
}

const APPROVAL_TONES: Record<string, StatusTone> = {
  pending: "warning",
  approved: "forest",
  executed: "forest",
  rejected: "danger",
  cancelled: "muted",
  expired: "muted",
};

export function approvalStatusTone(status: string): StatusTone {
  return APPROVAL_TONES[status] ?? "outline";
}

export function approvalStatusLabel(status: string): string {
  return status === "cancelled" ? "Cancelled" : status.charAt(0).toUpperCase() + status.slice(1);
}

export function approvalActionLabel(action: string): string {
  return action === "reactivate" ? "Reactivate" : action === "suspend" ? "Suspend" : action;
}

/** Deployment defaults; the API rejects anything larger even if this drifts. */
export const AUDIT_EXPORT_MAX_DAYS = 90;
export const AUDIT_EXPORT_MAX_ROWS = 5000;

export function platformStatusTone(status: string): StatusTone {
  return status === "suspended" ? "warning" : status === "active" ? "forest" : "outline";
}

export function healthStateLabel(state: string): string {
  if (state === "suspended") return "Suspended";
  if (state === "attention") return "Needs attention";
  if (state === "ok") return "Operational";
  return state;
}

export function healthStateTone(state: string): StatusTone {
  if (state === "suspended") return "warning";
  if (state === "attention") return "warning";
  if (state === "ok") return "forest";
  return "outline";
}

export const HEALTH_WARNING_COPY: Record<string, string> = {
  organization_suspended:
    "The tenant is suspended: members keep their accounts and memberships but cannot act inside it until it is reactivated.",
  no_active_members: "No member currently holds an active membership.",
  no_active_administrator:
    "No active organisation administrator. Nobody in the tenant can administer the roster.",
};

export function healthWarningCopy(code: string): string {
  return HEALTH_WARNING_COPY[code] ?? code.replace(/_/g, " ");
}

export const SUSPENSION_EFFECTS: readonly string[] = [
  "Existing sessions stay valid but stop granting this organisation; members fall back to another organisation if they have one.",
  "New sign-ins that select this organisation are refused until it is reactivated.",
  "Memberships, invitations, audit history and business records are not deleted.",
  "Memberships in other organisations are unaffected, and no user account is suspended.",
  "Inviting new members and accepting pending invitations are refused while suspended.",
];

/** Build a query string, dropping empty values so URLs stay canonical. */
export function platformQuery(
  params: Record<string, string | number | undefined | null>,
): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    const text = String(value).trim();
    if (!text) continue;
    query.set(key, text);
  }
  return query;
}

export function platformHref(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
): string {
  const suffix = platformQuery(params).toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function readParam(
  params: Record<string, string | string[] | undefined>,
  key: string,
): string {
  const value = params[key];
  return typeof value === "string" ? value : "";
}

/** Newest-first event ordering is the API's contract; this only labels it. */
export const AUDIT_ORDER_NOTE = "Newest first, ordered by timestamp then record id.";
