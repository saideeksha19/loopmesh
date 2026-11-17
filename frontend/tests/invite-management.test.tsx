import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteMemberForm } from "@/components/invitations/invite-form";
import { InvitationTable } from "@/components/invitations/invitation-table";
import type { Invitation } from "@/lib/account-types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

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

function invitation(overrides: Partial<Invitation> = {}): Invitation {
  return {
    id: "inv-1",
    email: "colleague@example.com",
    organization_id: "org-1",
    organization_name: "Aurelia Works",
    role: "reviewer",
    scope: "organization",
    status: "pending",
    expires_at: "2099-01-08T00:00:00Z",
    created_at: "2026-11-15T00:00:00Z",
    invited_by_user_id: "user-1",
    accepted_at: null,
    note: null,
    delivery_token: null,
    ...overrides,
  };
}

const ROLES = [
  { value: "coordinator", label: "Coordinator — proposes and records activity" },
  { value: "reviewer", label: "Reviewer — assesses proposals" },
];

function renderForm() {
  return render(
    <InviteMemberForm organizationId="org-1" organizationName="Aurelia Works" roles={ROLES} />,
  );
}

describe("invitation creation form", () => {
  beforeEach(() => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("posts the invitation with the organisation, role and note", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() =>
      jsonResponse(
        201,
        invitation({ delivery_token: "delivered-token-value", note: "Joining the steel pilot" }),
      ),
    );
    renderForm();

    await user.type(screen.getByLabelText("Email to invite"), "colleague@example.com");
    await user.selectOptions(screen.getByLabelText(/Role in Aurelia Works/), "reviewer");
    await user.type(screen.getByLabelText(/Note for the invitee/), "Joining the steel pilot");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/auth/invitations");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      email: "colleague@example.com",
      organization_id: "org-1",
      role: "reviewer",
      scope: "organization",
      note: "Joining the steel pilot",
    });
  });

  it("shows the development delivery link with an explicit warning", async () => {
    const user = userEvent.setup();
    mockFetch(() => jsonResponse(201, invitation({ delivery_token: "delivered-token-value" })));
    renderForm();

    await user.type(screen.getByLabelText("Email to invite"), "colleague@example.com");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(await screen.findByText(/Development delivery only/)).toBeInTheDocument();
    expect(screen.getByText(/\/invite\/delivered-token-value/)).toBeInTheDocument();
    expect(screen.getByText(/cannot be shown again/)).toBeInTheDocument();
  });

  it("rejects a malformed address without contacting the API", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() => jsonResponse(201, invitation()));
    renderForm();

    await user.type(screen.getByLabelText("Email to invite"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(
      screen.getByText("Enter a valid email address, for example name@company.com."),
    ).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("surfaces an authorization rejection", async () => {
    const user = userEvent.setup();
    mockFetch(() =>
      jsonResponse(403, {
        error: {
          code: "forbidden",
          message: "You do not have permission to invite members.",
          details: { required_permission: "invitation.manage" },
        },
      }),
    );
    renderForm();

    await user.type(screen.getByLabelText("Email to invite"), "colleague@example.com");
    await user.click(screen.getByRole("button", { name: "Create invitation" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to invite members.",
    );
  });
});

describe("pending invitation register", () => {
  beforeEach(() => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("shows pending invitations with role and expiry", () => {
    mockFetch(() => jsonResponse(200, invitation()));
    render(
      <InvitationTable
        initial={[invitation(), invitation({ id: "inv-2", email: "done@example.com", status: "accepted" })]}
      />,
    );

    expect(screen.getByText("colleague@example.com")).toBeInTheDocument();
    expect(screen.getAllByText("Reviewer").length).toBeGreaterThan(0);
    expect(screen.getByText(/expires 08 Jan 2099/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument();
    expect(screen.getByText("Earlier invitations")).toBeInTheDocument();
  });

  it("revokes a pending invitation only after the API confirms", async () => {
    const user = userEvent.setup();
    const calls = mockFetch(() => jsonResponse(200, invitation({ status: "revoked" })));
    render(<InvitationTable initial={[invitation()]} />);

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() =>
      expect(screen.getByText("Invitation for colleague@example.com revoked.")).toBeInTheDocument(),
    );
    expect(calls[0].url).toBe("/api/v1/auth/invitations/inv-1/revoke");
    expect(calls[0].init.method).toBe("POST");
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it("does nothing when the revocation is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = mockFetch(() => jsonResponse(200, invitation({ status: "revoked" })));
    render(<InvitationTable initial={[invitation()]} />);

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    expect(calls).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument();
  });

  it("explains an empty register", () => {
    mockFetch(() => jsonResponse(200, []));
    render(<InvitationTable initial={[]} />);

    expect(screen.getByText("No pending invitations")).toBeInTheDocument();
  });
});
