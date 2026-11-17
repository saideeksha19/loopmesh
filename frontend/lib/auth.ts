/**
 * Authentication types and pure helpers shared by server and client code.
 *
 * The browser never holds a credential in storage: the backend issues
 * HttpOnly session cookies and this module only mirrors the *presentation*
 * facts returned by `GET /auth/me`. Nothing here is an authorization
 * decision — the API re-checks every request.
 */

export const SESSION_COOKIE = "lm_session";
export const REFRESH_COOKIE = "lm_refresh";
export const CSRF_COOKIE = "lm_csrf";
/** Last visited workspace path, so a silent re-authentication can resume it. */
export const LAST_PATH_COOKIE = "lm_last_path";

export const LOGIN_PATH = "/login";
/** Account security lives outside the workspace shell so a forced rotation
 *  cannot bounce between a locked workspace and its own guard. */
export const ACCOUNT_PASSWORD_PATH = "/account/password";
export const ACCOUNT_SESSIONS_PATH = "/account/sessions";
export const FORCED_PASSWORD_PATH = `${ACCOUNT_PASSWORD_PATH}?required=1`;
/**
 * Silent renewal lives under the refresh cookie's path (`/api/v1/auth`), so
 * the browser actually presents that cookie. It must stay outside the
 * workspace layout to avoid a guard loop.
 */
export const RESUME_PATH = "/api/v1/auth/resume";

export type Membership = {
  id: string;
  organization_id: string;
  role: string;
  scope: string;
  status: string;
  organization_name: string | null;
  organization_slug: string | null;
};

export type SessionUser = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_platform_admin: boolean;
  is_development: boolean;
  must_change_password: boolean;
  active_organization_id: string | null;
  active_role: string | null;
  memberships: Membership[];
  permissions: string[];
  session_expires_at: string | null;
  csrf_token: string | null;
};

export type AuthMessage = {
  message: string;
  authenticated: boolean;
  user?: SessionUser | null;
};

export const ROLE_LABELS: Record<string, string> = {
  org_admin: "Organisation admin",
  coordinator: "Coordinator",
  reviewer: "Reviewer",
  approver: "Approver",
  auditor: "Auditor",
  viewer: "Viewer",
};

export function roleLabel(role: string | null | undefined): string {
  if (!role) return "No role";
  return ROLE_LABELS[role] ?? role.replace(/_/g, " ");
}

export function hasPermission(user: SessionUser | null, permission: string): boolean {
  return Boolean(user?.permissions?.includes(permission));
}

export function activeMembership(user: SessionUser): Membership | null {
  return (
    user.memberships.find((membership) => membership.organization_id === user.active_organization_id) ??
    null
  );
}

export function displayName(user: Pick<SessionUser, "full_name" | "email">): string {
  return user.full_name?.trim() || user.email;
}

export function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  if (parts.length === 0) return "LM";
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("");
}

/**
 * Only same-origin, workspace-relative destinations are honoured after a
 * sign-in or a renewal. Protocol-relative (`//host`), absolute URLs, control
 * characters and the auth pages themselves are rejected to prevent open
 * redirects and loops. Valid destinations are preserved; fallback is the workspace overview.
 */
export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return "/overview";
  if (raw.length > 512) return "/overview";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/overview";
  if (raw.includes("\\") || /[\u0000-\u001f]/.test(raw)) return "/overview";
  const path = raw.split("#")[0];
  const base = path.split("?")[0];
  if (base === LOGIN_PATH || base.startsWith(`${LOGIN_PATH}/`)) return "/overview";
  if (base === RESUME_PATH || base.startsWith("/api/")) return "/overview";
  return path;
}

/** A same-origin location the workspace guard may redirect to. */
/**
 * Where an unauthenticated workspace request goes.
 *
 * Always the renewal endpoint: the refresh cookie is scoped to
 * `/api/v1/auth`, so a workspace request cannot even see it. The endpoint
 * decides between a silent renewal and the sign-in page, which also makes a
 * lapsed access cookie recoverable after a browser restart.
 */
export type SessionRedirect = string;

export function sessionRedirectTarget(): SessionRedirect {
  return RESUME_PATH;
}

export const LOGIN_REASON_COPY: Record<string, string> = {
  signed_out: "You have been signed out. Sign in to return to the workspace.",
  session_expired: "Your session expired. Sign in again to continue where you left off.",
  session_revoked: "This session was revoked. Sign in again to continue.",
  required: "Sign in to open the LOOPMESH workspace.",
  password_changed: "Your password changed, so every session was closed. Sign in again.",
  password_change_required: "Set your own password before opening the workspace.",
  api_unavailable: "The LOOPMESH API is not reachable, so the session could not be renewed. Start the backend and sign in again.",
};
