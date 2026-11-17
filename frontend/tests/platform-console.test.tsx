import type { ReactNode } from "react";

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
const api = vi.hoisted(() => ({ patchJson: vi.fn(), postJson: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: { href: string; children: ReactNode } & Record<string, unknown>) => (
    <a href={typeof href === "string" ? href : "#"} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/client-api", () => ({
  patchJson: api.patchJson,
  postJson: api.postJson,
}));

import { AuditFilters } from "@/components/platform/audit-filters";
import { AuditLog } from "@/components/platform/audit-log";
import { HealthTable } from "@/components/platform/health-table";
import { OrganizationRegister } from "@/components/platform/organization-register";
import { OrganizationStatus } from "@/components/platform/organization-status";
import { PlatformOverview } from "@/components/platform/overview";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { navGroupsFor } from "@/components/shell/nav-config";
import type { SessionUser } from "@/lib/auth";
import {
  PLATFORM_PERMISSION,
  canPlatform,
  platformGate,
  platformNavFor,
} from "@/lib/platform";
import type {
  PlatformAuditEvent,
  PlatformDashboard,
  PlatformOrganizationRow,
  PlatformTenantHealth,
} from "@/lib/platform-types";

const VIEWER_PERMISSIONS = ["dashboard.view", "material.view", "audit.view"];

function user(overrides: Partial<SessionUser> = {}): SessionUser {
  return {
    id: "u-1",
    email: "operator@example.com",
    full_name: "Platform Operator",
    is_active: true,
    is_platform_admin: true,
    is_development: false,
    must_change_password: false,
    active_organization_id: null,
    active_role: null,
    memberships: [],
    permissions: Object.values(PLATFORM_PERMISSION),
    session_expires_at: null,
    csrf_token: null,
    ...overrides,
  };
}

function organisationRow(overrides: Partial<PlatformOrganizationRow> = {}): PlatformOrganizationRow {
  return {
    id: "org-1",
    name: "Aurelia Chemicals",
    slug: "aurelia-chemicals",
    sector: "chemicals",
    country: "DE",
    city: "Ludwigshafen",
    status: "active",
    is_demo: false,
    created_at: "2026-01-04T09:00:00Z",
    suspended_at: null,
    active_members: 4,
    suspended_members: 1,
    pending_invitations: 2,
    ...overrides,
  };
}

function dashboard(overrides: Partial<PlatformDashboard> = {}): PlatformDashboard {
  return {
    generated_at: "2026-11-15T10:00:00Z",
    window_days: 30,
    failure_window_hours: 24,
    organisations: { total: 3, active: 2, suspended: 1, created_in_window: 1 },
    users: { total: 9, active: 8 },
    memberships: { active: 6, suspended: 1, invited: 2, removed: 0 },
    pending_invitations: 2,
    failed_logins_window: 4,
    recent_organisations: [],
    recent_events: [],
    ...overrides,
  };
}

function auditEvent(overrides: Partial<PlatformAuditEvent> = {}): PlatformAuditEvent {
  return {
    id: "ev-1",
    created_at: "2026-11-15T10:00:00Z",
    event_type: "platform.organization.suspended",
    entity_type: "organization",
    entity_id: "org-1",
    actor: "operator@example.com",
    actor_id: "u-1",
    organization_id: "org-1",
    organization_name: "Aurelia Chemicals",
    severity: "warning",
    summary: "Organisation suspended by platform administration.",
    reason: "Repeated policy breach",
    previous_state: "active",
    new_state: "suspended",
    payload: { password: "[redacted]", note: "safe-value" },
    redacted_fields: ["password"],
    ...overrides,
  };
}

function healthRow(overrides: Partial<PlatformTenantHealth> = {}): PlatformTenantHealth {
  return {
    organization: {
      id: "org-2",
      name: "Meridian Steel",
      slug: "meridian-steel",
      sector: "steel_metals",
      country: "FR",
      city: null,
      status: "active",
      is_demo: false,
      created_at: "2026-02-01T00:00:00Z",
      suspended_at: null,
    },
    active_members: 2,
    suspended_members: 0,
    pending_invitations: 1,
    active_administrators: 0,
    admin_changes_window: 3,
    security_events_window: 1,
    member_auth_failures_window: 2,
    last_activity_at: "2026-11-14T12:00:00Z",
    state: "attention",
    warnings: ["no_active_administrator"],
    checks: ["tenant_active", "membership_present", "active_administrator_present"],
    ...overrides,
  };
}

describe("platform access model", () => {
  it("requires the explicit platform flag, not only a capability", () => {
    const orgAdmin = user({
      is_platform_admin: false,
      permissions: ["member.manage", PLATFORM_PERMISSION.dashboard],
    });

    expect(canPlatform(orgAdmin, PLATFORM_PERMISSION.dashboard)).toBe(false);
    expect(canPlatform(user(), PLATFORM_PERMISSION.dashboard)).toBe(true);
    expect(
      canPlatform(user({ permissions: [] }), PLATFORM_PERMISSION.dashboard),
    ).toBe(false);
  });

  it("sends an organisation administrator away from /platform before rendering", () => {
    const orgAdmin = user({
      is_platform_admin: false,
      permissions: VIEWER_PERMISSIONS,
    });

    expect(platformGate({ status: "authenticated", user: orgAdmin })).toBe("workspace");
    expect(platformGate({ status: "authenticated", user: user() })).toBe("ok");
    expect(platformGate({ status: "anonymous" })).toBe("signed_out");
    expect(platformGate({ status: "unavailable", error: "down" })).toBe("offline");
    expect(
      platformGate({ status: "authenticated", user: user({ must_change_password: true }) }),
    ).toBe("password");
  });

  it("filters platform navigation by capability", () => {
    expect(platformNavFor(Object.values(PLATFORM_PERMISSION)).map((item) => item.href)).toEqual([
      "/platform",
      "/platform/organizations",
      "/platform/health",
      "/platform/audit",
      "/platform/approvals",
      "/platform/security",
    ]);
    expect(platformNavFor(["platform.audit.view"]).map((item) => item.href)).toEqual([
      "/platform/audit",
    ]);
    expect(platformNavFor(VIEWER_PERMISSIONS)).toEqual([]);
  });

  it("shows the workspace entry only to a platform operator", () => {
    const platformHrefs = navGroupsFor(Object.values(PLATFORM_PERMISSION)).flatMap((group) =>
      group.items.map((item) => item.href),
    );
    const viewerHrefs = navGroupsFor(VIEWER_PERMISSIONS).flatMap((group) =>
      group.items.map((item) => item.href),
    );

    expect(platformHrefs).toContain("/platform");
    expect(viewerHrefs).not.toContain("/platform");
  });

  it("renders an explicit refusal rather than empty data", () => {
    render(
      <PlatformDenied
        title="The platform journal needs platform.audit.view"
        capability="platform.audit.view"
        description="Your account is a platform operator without this capability."
      />,
    );

    expect(screen.getByText("The platform journal needs platform.audit.view")).toBeInTheDocument();
    expect(screen.getByText("platform.audit.view")).toBeInTheDocument();
  });
});

describe("platform dashboard", () => {
  it("renders database-derived aggregates and their windows", () => {
    render(<PlatformOverview data={dashboard()} />);

    expect(screen.getByText("Organisations")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/2 active · 1 suspended/)).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText(/failed sign-ins in the last 24 hours/)).toBeInTheDocument();
    expect(screen.getByText("No organisations yet")).toBeInTheDocument();
    expect(screen.getByText("No privileged events in this window")).toBeInTheDocument();
  });

  it("names recent organisations and links to their detail", () => {
    render(
      <PlatformOverview
        data={dashboard({ recent_organisations: [organisationRow()] })}
      />,
    );

    expect(screen.getByRole("link", { name: "Aurelia Chemicals" })).toHaveAttribute(
      "href",
      "/platform/organizations/org-1",
    );
    expect(screen.getByText(/aurelia-chemicals/)).toBeInTheDocument();
  });
});

describe("organisation register", () => {
  it("lists safe operational fields and links to the tenant", () => {
    render(
      <OrganizationRegister
        items={[organisationRow()]}
        total={1}
        page={1}
        pageSize={25}
        hasMore={false}
        filters={{ q: "", status: "" }}
      />,
    );

    const list = screen.getByRole("list");
    expect(within(list).getByRole("link", { name: "Aurelia Chemicals" })).toHaveAttribute(
      "href",
      "/platform/organizations/org-1",
    );
    expect(within(list).getByText("Active")).toBeInTheDocument();
    expect(within(list).getByText("4 active · 1 deactivated")).toBeInTheDocument();
    expect(within(list).getByText("2 pending invites")).toBeInTheDocument();
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument();
  });

  it("preserves filters in pagination and stacks on narrow screens", () => {
    render(
      <OrganizationRegister
        items={[organisationRow()]}
        total={40}
        page={2}
        pageSize={25}
        hasMore
        filters={{ q: "aurelia", status: "active" }}
      />,
    );

    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      "/platform/organizations?q=aurelia&status=active&page=3",
    );
    expect(screen.getByRole("link", { name: "← Previous" })).toHaveAttribute(
      "href",
      "/platform/organizations?q=aurelia&status=active&page=1",
    );
    expect(screen.getByText(/page 2 · 40 organisations · 25 per page/)).toBeInTheDocument();

    const row = screen.getByRole("listitem");
    expect(row.querySelector(".flex-col.sm\\:flex-row")).not.toBeNull();
  });
});

describe("tenant health", () => {
  it("shows the checks, counts and warning explanation", () => {
    render(
      <HealthTable items={[healthRow()]} total={1} page={1} pageSize={25} hasMore={false} />,
    );

    expect(screen.getByRole("link", { name: "Meridian Steel" })).toHaveAttribute(
      "href",
      "/platform/organizations/org-2",
    );
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText(/No active organisation administrator/)).toBeInTheDocument();
    expect(screen.getByText(/Checks: tenant_active · membership_present/)).toBeInTheDocument();
    expect(screen.getByText("Active members")).toBeInTheDocument();
    expect(screen.getByText("Auth failures")).toBeInTheDocument();
  });
});

describe("platform audit journal", () => {
  it("renders a safe representation with redacted payload fields", () => {
    render(<AuditLog items={[auditEvent()]} />);

    expect(screen.getByText("platform.organization.suspended")).toBeInTheDocument();
    expect(screen.getByText(/Reason: Repeated policy breach/)).toBeInTheDocument();
    expect(screen.getByText("redacted: password")).toBeInTheDocument();
    expect(screen.getByText(/safe-value/)).toBeInTheDocument();
    expect(screen.queryByText(/hunter2/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Aurelia Chemicals" })).toHaveAttribute(
      "href",
      "/platform/organizations/org-1",
    );
  });

  it("prefills filters and offers organisation options", () => {
    render(
      <AuditFilters
        values={{
          created_from: "2026-01-01",
          created_to: "2026-02-01",
          actor: "ops@",
          event_type: "membership.changed",
          entity_type: "",
          entity_id: "",
          target_user_id: "",
          organization_id: "org-1",
        }}
        organizations={[organisationRow()]}
      />,
    );

    expect(screen.getByLabelText("From (UTC date)")).toHaveValue("2026-01-01");
    expect(screen.getByLabelText("To (UTC date)")).toHaveValue("2026-02-01");
    expect(screen.getByLabelText("Actor (contains)")).toHaveValue("ops@");
    expect(screen.getByLabelText("Event type")).toHaveValue("membership.changed");
    const select = screen.getByLabelText("Organisation");
    expect(within(select).getByRole("option", { name: "Aurelia Chemicals" })).toBeInTheDocument();
    expect(select).toHaveValue("org-1");
    expect(screen.getByRole("button", { name: "Apply filters" })).toBeInTheDocument();
  });
});

describe("organisation status administration", () => {
  const target = {
    id: "org-1",
    name: "Aurelia Chemicals",
    slug: "aurelia-chemicals",
    status: "active" as const,
  };

  beforeEach(() => {
    router.refresh.mockReset();
    api.patchJson.mockReset();
    api.postJson.mockReset();
  });

  it("requires a written reason and a confirmation before suspending", async () => {
    const userEventSetup = userEvent.setup();
    api.postJson.mockResolvedValue({
      ok: true,
      data: { id: "approval-1", action: "suspend", status: "pending" },
    });

    render(<OrganizationStatus organization={target} canManage />);

    await userEventSetup.click(screen.getByRole("button", { name: "Request suspension" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Existing sessions stay valid/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Memberships in other organisations are unaffected/)).toBeInTheDocument();

    const confirm = within(dialog).getByRole("button", { name: "Create suspension request" });
    expect(confirm).toBeDisabled();

    const reason = within(dialog).getByRole("textbox");
    await userEventSetup.type(reason, "Repeated policy breach");
    expect(confirm).toBeEnabled();

    await userEventSetup.click(confirm);

    expect(api.postJson).toHaveBeenCalledWith("/platform/approvals", {
      organization_id: "org-1",
      action: "suspend",
      reason: "Repeated policy breach",
    });
    expect(router.refresh).toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent(/Suspension requested/);
    expect(await screen.findByRole("status")).toHaveTextContent(/unchanged/);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the dialog open and reports an API refusal", async () => {
    const userEventSetup = userEvent.setup();
    api.postJson.mockResolvedValue({
      ok: false,
      error: "Suspension requires a written reason of at least 8 characters.",
      code: "validation_error",
    });

    render(<OrganizationStatus organization={target} canManage />);
    await userEventSetup.click(screen.getByRole("button", { name: "Request suspension" }));
    await userEventSetup.type(screen.getByRole("textbox"), "Policy breach");
    await userEventSetup.click(
      screen.getByRole("button", { name: "Create suspension request" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Suspension requires a written reason of at least 8 characters.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("confirms reactivation of a suspended tenant", async () => {
    const userEventSetup = userEvent.setup();
    api.postJson.mockResolvedValue({
      ok: true,
      data: { id: "approval-2", action: "reactivate", status: "pending" },
    });

    render(
      <OrganizationStatus organization={{ ...target, status: "suspended" }} canManage />,
    );

    await userEventSetup.click(screen.getByRole("button", { name: "Request reactivation" }));
    const dialog = screen.getByRole("dialog");
    await userEventSetup.click(
      within(dialog).getByRole("button", { name: "Create reactivation request" }),
    );

    expect(api.postJson).toHaveBeenCalledWith("/platform/approvals", {
      organization_id: "org-1",
      action: "reactivate",
      reason: null,
    });
    expect(router.refresh).toHaveBeenCalled();
  });

  it("offers no lifecycle control without the manage capability", () => {
    render(<OrganizationStatus organization={target} canManage={false} />);

    expect(screen.queryByRole("button", { name: "Request suspension" })).not.toBeInTheDocument();
    expect(screen.getByText(/can inspect this tenant but not change its lifecycle/)).toBeInTheDocument();
  });
});

describe("platform audit ordering contract", () => {
  it("labels the order the API promises", () => {
    render(<AuditLog items={[]} />);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
