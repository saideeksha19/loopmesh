import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/components/auth/login-form";
import { navGroupsFor } from "@/components/shell/nav-config";
import { deviceLabel, invitableRoles, isExpired } from "@/lib/account-types";
import { passwordProblem } from "@/lib/password-policy";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const MEMBER_PERMISSIONS = [
  "dashboard.view",
  "material.view",
  "network.view",
  "member.view",
  "proposal.view",
];

describe("onboarding navigation", () => {
  beforeEach(() => {
    router.replace.mockReset();
    router.refresh.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, {})),
    );
  });

  it("shows the members register only to roles that can read it", () => {
    const withMember = navGroupsFor(MEMBER_PERMISSIONS).flatMap((group) =>
      group.items.map((item) => item.href),
    );
    const withoutMember = navGroupsFor(
      MEMBER_PERMISSIONS.filter((permission) => permission !== "member.view"),
    ).flatMap((group) => group.items.map((item) => item.href));

    expect(withMember).toContain("/members");
    expect(withoutMember).not.toContain("/members");
  });

  it("offers the org-admin role only to administrators who can manage members", () => {
    const coordinator = invitableRoles(["invitation.manage"]).map((role) => role.value);
    const admin = invitableRoles(["invitation.manage", "member.manage"]).map((role) => role.value);

    expect(coordinator).toContain("viewer");
    expect(coordinator).not.toContain("org_admin");
    expect(admin).toContain("org_admin");
    // Platform scope is never offered: only a platform administrator can grant it.
    expect(admin.join(",")).not.toContain("platform");
  });

  it("summarises a session's client without exposing anything identifying", () => {
    expect(
      deviceLabel("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Safari/605"),
    ).toBe("Safari on macOS");
    expect(deviceLabel(null)).toBe("Unknown device");
  });

  it("treats a lapsed invitation as expired", () => {
    expect(isExpired("2020-01-01T00:00:00Z")).toBe(true);
    expect(isExpired("2099-01-01T00:00:00Z")).toBe(false);
  });

  it("mirrors the server password policy in the browser", () => {
    expect(passwordProblem("Short!1")).toMatch(/12 characters/);
    expect(passwordProblem("alllowercasepass")).toMatch(/Upper and lower case/);
    expect(passwordProblem("NoSymbolsHereAtAll")).toMatch(/number or symbol/);
    expect(passwordProblem("aaaaAAAA1111aaaa")).toMatch(/different characters/);
    expect(passwordProblem("StrongPass!2345")).toBeNull();
  });

  it("sends an account with an operator-issued password to rotation, not the workspace", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, {
          message: "Signed in.",
          authenticated: true,
          user: {
            id: "u1",
            email: "rotating@example.com",
            full_name: "Rotating Person",
            must_change_password: true,
          },
        }),
      ),
    );

    render(<LoginForm next="/materials" />);
    await user.type(screen.getByLabelText("Work email"), "rotating@example.com");
    await user.type(screen.getByLabelText("Password"), "InitialPass!2345");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/account/password?required=1"),
    );
    expect(router.replace).not.toHaveBeenCalledWith("/materials");
  });

  it("keeps the requested destination for an ordinary sign-in", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, {
          message: "Signed in.",
          authenticated: true,
          user: {
            id: "u2",
            email: "ada@aurelia.example",
            full_name: "Ada Ortega",
            must_change_password: false,
          },
        }),
      ),
    );

    render(<LoginForm next="/materials" />);
    await user.type(screen.getByLabelText("Work email"), "ada@aurelia.example");
    await user.type(screen.getByLabelText("Password"), "LoopmeshDemo!2026");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/materials"));
  });
});
