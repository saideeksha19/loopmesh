import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrgSwitcher } from "@/components/auth/org-switcher";
import { UserMenu } from "@/components/auth/user-menu";
import { SidebarContent } from "@/components/shell/sidebar-content";
import { navGroupsFor } from "@/components/shell/nav-config";
import type { SessionUser } from "@/lib/auth";

const router = vi.hoisted(() => ({ refresh: vi.fn(), replace: vi.fn(), push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/",
}));

const VIEWER_PERMISSIONS = [
  "organization.view",
  "member.view",
  "material.view",
  "demand.view",
  "opportunity.view",
  "network.view",
  "proposal.view",
  "transaction.view",
  "ledger.view",
  "dashboard.view",
  "agent.view",
  "optimization.view",
];

function buildUser(overrides: Partial<SessionUser> = {}): SessionUser {
  return {
    id: "user-1",
    email: "ada@aurelia.example",
    full_name: "Ada Ortega",
    is_active: true,
    is_platform_admin: false,
    is_development: false,
    must_change_password: false,
    active_organization_id: "org-a",
    active_role: "coordinator",
    memberships: [
      {
        id: "m-a",
        organization_id: "org-a",
        role: "coordinator",
        scope: "organization",
        status: "active",
        organization_name: "Alpha Metals",
        organization_slug: "alpha-metals",
      },
      {
        id: "m-b",
        organization_id: "org-b",
        role: "viewer",
        scope: "organization",
        status: "active",
        organization_name: "Beta Polymers",
        organization_slug: "beta-polymers",
      },
    ],
    permissions: [...VIEWER_PERMISSIONS, "audit.view"],
    session_expires_at: new Date(Date.now() + 900_000).toISOString(),
    csrf_token: "nonce",
    ...overrides,
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("organisation switcher", () => {
  beforeEach(() => {
    router.refresh.mockReset();
    document.cookie = "lm_csrf=nonce; path=/";
  });

  it("lists only the memberships the API returned and switches the active one", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
        calls.push({ url: String(input), init });
        return jsonResponse(200, { ...buildUser(), active_organization_id: "org-b" });
      }),
    );

    render(<OrgSwitcher user={buildUser()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Switch organisation/ }));

    const menu = screen.getByRole("menu", { name: "Switch organisation" });
    expect(menu).toHaveTextContent("Alpha Metals");
    expect(menu).toHaveTextContent("Beta Polymers");
    expect(screen.getAllByRole("menuitemradio")).toHaveLength(2);
    expect(screen.getByRole("menuitemradio", { name: /Alpha Metals/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await userEvent.setup().click(screen.getByRole("menuitemradio", { name: /Beta Polymers/ }));

    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls[0].url).toBe("/api/v1/auth/switch-organization");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ organization_id: "org-b" });
    expect(new Headers(calls[0].init.headers).get("X-CSRF-Token")).toBe("nonce");
  });

  it("reports a refused switch and keeps the current organisation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(403, {
          error: {
            code: "authorization_error",
            message: "You are not a member of that organisation.",
            details: { reason: "membership_required" },
          },
        }),
      ),
    );

    render(<OrgSwitcher user={buildUser()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Switch organisation/ }));
    await userEvent.setup().click(screen.getByRole("menuitemradio", { name: /Beta Polymers/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You are not a member of that organisation.",
    );
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("renders a static label when the user belongs to a single organisation", () => {
    const single = buildUser({ memberships: [buildUser().memberships[0]] });

    render(<OrgSwitcher user={single} />);

    expect(screen.getByText("Alpha Metals")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Switch organisation/ })).not.toBeInTheDocument();
  });
});

describe("account menu", () => {
  beforeEach(() => {
    document.cookie = "lm_csrf=nonce; path=/";
  });

  it("shows the current user's role and organisation", async () => {
    render(<UserMenu user={buildUser()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Account menu for Ada Ortega/ }));

    expect(screen.getByRole("menu", { name: "Account" })).toHaveTextContent("ada@aurelia.example");
    expect(screen.getByText("Coordinator")).toBeInTheDocument();
    expect(screen.getByText("Alpha Metals")).toBeInTheDocument();
  });

  it("invalidates the backend session before leaving the workspace", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", search: "", assign });
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        calls.push(String(input));
        return jsonResponse(200, { message: "Signed out.", authenticated: false });
      }),
    );

    render(<UserMenu user={buildUser()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Account menu/ }));
    await userEvent.setup().click(screen.getByRole("menuitem", { name: "Sign out" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/login?reason=signed_out"));
    expect(calls).toEqual(["/api/v1/auth/logout"]);
  });

  it("does not claim a sign-out when the API refuses it", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", search: "", assign });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(503, {
          error: { code: "api_unreachable", message: "The LOOPMESH API is not reachable." },
        }),
      ),
    );

    render(<UserMenu user={buildUser()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Account menu/ }));
    await userEvent.setup().click(screen.getByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not reachable");
    expect(assign).not.toHaveBeenCalled();
  });
});

describe("role-based navigation", () => {
  it("hides the audit journal from roles without audit.view", async () => {
    const groups = navGroupsFor(VIEWER_PERMISSIONS);
    const hrefs = groups.flatMap((group) => group.items.map((item) => item.href));

    expect(hrefs).not.toContain("/audit");
    expect(hrefs).toContain("/materials");
    expect(navGroupsFor([...VIEWER_PERMISSIONS, "audit.view"]).flatMap((group) =>
      group.items.map((item) => item.href),
    )).toContain("/audit");

    render(<SidebarContent apiOnline permissions={VIEWER_PERMISSIONS} />);
    expect(screen.queryByRole("link", { name: /Audit journal/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Material intelligence/ })).toBeInTheDocument();
  });
});
