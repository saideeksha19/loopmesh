import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MemberRoster } from "@/components/members/member-roster";
import type { Member } from "@/lib/account-types";

type Call = { url: string; init: RequestInit };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function mockFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      calls.push({ url, init });
      return handler(url, init);
    }),
  );
  return calls;
}

function member(overrides: Partial<Member> = {}): Member {
  return {
    id: "m-1",
    user_id: "u-1",
    full_name: "Beta Viewer",
    email: "beta@example.com",
    role: "viewer",
    scope: "organization",
    status: "active",
    joined_at: "2026-11-15T00:00:00Z",
    is_self: false,
    ...overrides,
  };
}

const ADMIN = member({
  id: "m-admin",
  user_id: "u-admin",
  full_name: "Alpha Admin",
  email: "admin@example.com",
  role: "org_admin",
  is_self: true,
});

describe("member roster", () => {
  beforeEach(() => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("shows role, status and joined date for every member", () => {
    mockFetch(() => jsonResponse(200, []));
    render(<MemberRoster initial={[ADMIN, member()]} canManage />);

    const list = screen.getByRole("list");
    expect(within(list).getByText("Alpha Admin")).toBeInTheDocument();
    expect(within(list).getByText("Beta Viewer")).toBeInTheDocument();
    expect(within(list).getAllByText("Viewer").length).toBeGreaterThan(0);
    expect(within(list).getAllByText("Active").length).toBe(2);
    expect(within(list).getAllByText(/joined 15 Nov 2026/).length).toBe(2);
  });

  it("explains that the caller's own membership is managed elsewhere", () => {
    render(<MemberRoster initial={[ADMIN, member()]} canManage />);

    expect(
      screen.getByText(/Your own membership is managed by another administrator/),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(`Role for ${ADMIN.email}`)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Role for beta@example.com")).toBeInTheDocument();
  });

  it("renders a read-only register without management controls", () => {
    render(<MemberRoster initial={[member()]} canManage={false} />);

    expect(screen.queryByLabelText("Role for beta@example.com")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reset password" })).not.toBeInTheDocument();
    expect(screen.getByText("Viewer")).toBeInTheDocument();
  });

  it("filters by search term and status", async () => {
    const user = userEvent.setup();
    render(
      <MemberRoster
        initial={[ADMIN, member(), member({ id: "m-3", full_name: "Gamma Auditor", email: "gamma@example.com", role: "auditor", status: "suspended" })]}
        canManage
      />,
    );

    await user.type(screen.getByLabelText("Search members"), "gamma");
    expect(screen.getByText("Gamma Auditor")).toBeInTheDocument();
    expect(screen.queryByText("Beta Viewer")).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText("Search members"));
    await user.selectOptions(screen.getByLabelText("Filter by status"), "suspended");
    const list = screen.getByRole("list");
    expect(within(list).getByText("Gamma Auditor")).toBeInTheDocument();
    expect(within(list).queryByText("Beta Viewer")).not.toBeInTheDocument();
  });

  it("changes a role only after confirmation and shows the server result", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() => jsonResponse(200, member({ role: "reviewer" })));
    render(<MemberRoster initial={[member()]} canManage />);

    await user.selectOptions(screen.getByLabelText("Role for beta@example.com"), "reviewer");
    await user.click(screen.getByRole("button", { name: "Save role" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/organizations/members/m-1");
    expect(calls[0].init.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ role: "reviewer" });
    expect(screen.getByRole("status")).toHaveTextContent("Beta Viewer is now Reviewer.");
  });

  it("does not change a role when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = mockFetch(() => jsonResponse(200, member({ role: "reviewer" })));
    render(<MemberRoster initial={[member()]} canManage />);

    await user.selectOptions(screen.getByLabelText("Role for beta@example.com"), "reviewer");
    await user.click(screen.getByRole("button", { name: "Save role" }));

    expect(calls).toHaveLength(0);
    expect(screen.getByLabelText("Role for beta@example.com")).toHaveValue("viewer");
  });

  it("surfaces a last-administrator refusal from the API", async () => {
    const user = userEvent.setup();
    mockFetch(() =>
      jsonResponse(409, {
        error: {
          code: "conflict",
          message:
            "The organisation must keep at least one active administrator. Appoint a replacement before changing this membership.",
          details: { reason: "last_admin" },
        },
      }),
    );
    render(<MemberRoster initial={[member()]} canManage />);

    await user.selectOptions(screen.getByLabelText("Role for beta@example.com"), "coordinator");
    await user.click(screen.getByRole("button", { name: "Save role" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The organisation must keep at least one active administrator.",
    );
  });

  it("deactivates a member and reports the revoked sessions", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() =>
      jsonResponse(200, { member: member({ status: "suspended" }), sessions_revoked: 2 }),
    );
    render(<MemberRoster initial={[member()]} canManage />);

    await user.click(screen.getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(calls[0].url).toBe("/api/v1/organizations/members/m-1/deactivate");
    expect(calls[0].init.method).toBe("POST");
    expect(within(screen.getByRole("list")).getByText("Deactivated")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("2 session(s) revoked");
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("memberships in other organisations are not affected"),
    );
  });

  it("does nothing when deactivation is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = mockFetch(() => jsonResponse(200, { member: member(), sessions_revoked: 0 }));
    render(<MemberRoster initial={[member()]} canManage />);

    await user.click(screen.getByRole("button", { name: "Deactivate" }));

    expect(calls).toHaveLength(0);
    expect(within(screen.getByRole("list")).getByText("Active")).toBeInTheDocument();
  });

  it("reactivates a suspended membership", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() =>
      jsonResponse(200, { member: member({ status: "active" }), sessions_revoked: 0 }),
    );
    render(<MemberRoster initial={[member({ status: "suspended" })]} canManage />);

    await user.click(screen.getByRole("button", { name: "Reactivate" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(calls[0].url).toBe("/api/v1/organizations/members/m-1/reactivate");
    expect(within(screen.getByRole("list")).getByText("Active")).toBeInTheDocument();
  });

  it("issues a password reset after explaining its consequences", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() =>
      jsonResponse(200, {
        member: member(),
        sessions_revoked: 3,
        must_change_password: true,
        message: "Password reset issued.",
      }),
    );
    render(<MemberRoster initial={[member()]} canManage />);

    await user.click(screen.getByRole("button", { name: "Reset password" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(calls[0].url).toBe("/api/v1/organizations/members/m-1/reset-password");
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("must set a new password before entering the workspace"),
    );
    expect(screen.getByRole("status")).toHaveTextContent("3 session(s) revoked");
  });

  it("explains an empty register", () => {
    render(<MemberRoster initial={[]} canManage />);
    expect(screen.getByText("No members yet")).toBeInTheDocument();
  });

  it("explains a filter that matches nothing", async () => {
    const user = userEvent.setup();
    render(<MemberRoster initial={[member()]} canManage />);

    await user.type(screen.getByLabelText("Search members"), "zzz");
    expect(screen.getByText("No members match")).toBeInTheDocument();
  });
});
