import type { ReactNode } from "react";

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ refresh: vi.fn() }));
const api = vi.hoisted(() => ({ postJson: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: { href: string; children: ReactNode } & Record<string, unknown>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/client-api", () => ({ postJson: api.postJson }));

import { ApprovalRequestForm } from "@/components/platform/approval-request-form";
import { ApprovalReview } from "@/components/platform/approval-review";
import { AuditExport } from "@/components/platform/audit-export";
import { MfaPanel } from "@/components/platform/mfa-panel";
import { OperatorSessions } from "@/components/platform/operator-sessions";
import type {
  MfaStatus,
  PlatformApproval,
  PlatformOperatorSession,
  PlatformOrganizationRow,
} from "@/lib/platform-types";

const organization = {
  id: "org-1",
  name: "Aurelia Chemicals",
  slug: "aurelia-chemicals",
  sector: "chemicals",
  country: "DE",
  city: "Ludwigshafen",
  status: "active",
  is_demo: false,
  created_at: "2026-01-01T00:00:00Z",
  suspended_at: null,
  active_members: 4,
  suspended_members: 0,
  pending_invitations: 0,
} as PlatformOrganizationRow;

function approval(overrides: Partial<PlatformApproval> = {}): PlatformApproval {
  return {
    id: "approval-1",
    organization_id: "org-1",
    organization_name: "Aurelia Chemicals",
    organization_slug: "aurelia-chemicals",
    organization_status: "active",
    action: "suspend",
    reason: "Repeated policy breach",
    status: "approved",
    requested_by_user_id: "u-1",
    requested_by: "requester@example.com",
    created_at: "2026-01-01T00:00:00Z",
    expires_at: "2026-01-01T01:00:00Z",
    decided_by_user_id: "u-2",
    decided_by: "approver@example.com",
    decided_at: "2026-01-01T00:10:00Z",
    decision_reason: null,
    executed_by_user_id: null,
    executed_by: null,
    executed_at: null,
    is_expired: false,
    can_decide: false,
    can_execute: true,
    can_cancel: false,
    ...overrides,
  };
}

const session = (overrides: Partial<PlatformOperatorSession> = {}): PlatformOperatorSession => ({
  id: "session-1",
  user_id: "u-2",
  user_email: "other@example.com",
  created_at: "2026-01-01T00:00:00Z",
  last_seen_at: "2026-01-01T00:05:00Z",
  mfa_verified_at: "2026-01-01T00:01:00Z",
  revoked_at: null,
  revoked_reason: null,
  is_current: false,
  user_agent: null,
  ...overrides,
});

beforeEach(() => {
  router.refresh.mockReset();
  api.postJson.mockReset();
});

describe("approval request", () => {
  it("creates a request without claiming the tenant changed", async () => {
    const user = userEvent.setup();
    api.postJson.mockResolvedValue({ ok: true, data: approval({ status: "pending" }) });
    render(<ApprovalRequestForm organizations={[organization]} canRequest />);

    await user.selectOptions(screen.getByRole("combobox", { name: /Organisation/ }), "org-1");
    await user.type(screen.getByRole("textbox"), "Repeated policy breach");
    await user.click(screen.getByRole("button", { name: "Request approval" }));

    expect(api.postJson).toHaveBeenCalledWith("/platform/approvals", {
      organization_id: "org-1",
      action: "suspend",
      reason: "Repeated policy breach",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/pending a different operator/);
    expect(screen.getByRole("status")).toHaveTextContent(/Nothing has changed/);
  });

  it("does not render the form without the request capability", () => {
    render(<ApprovalRequestForm organizations={[organization]} canRequest={false} />);
    expect(screen.queryByRole("button", { name: "Request approval" })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot create one/)).toBeInTheDocument();
  });
});

describe("approval review", () => {
  it("confirms execution and reports the terminal result", async () => {
    const user = userEvent.setup();
    api.postJson.mockResolvedValue({
      ok: true,
      data: approval({ status: "executed", executed_at: "2026-01-01T00:20:00Z" }),
    });
    render(<ApprovalReview approval={approval()} />);

    await user.click(screen.getByRole("button", { name: "Execute suspend" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/approved by/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Execute change" }));

    expect(api.postJson).toHaveBeenCalledWith("/platform/approvals/approval-1/execute", {});
    expect(await screen.findByRole("status")).toHaveTextContent(/was executed/);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("does not offer approval to the requester", () => {
    render(<ApprovalReview approval={approval({ can_execute: false, can_decide: false })} />);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByText(/No action is available/)).toBeInTheDocument();
  });
});

describe("operator MFA", () => {
  const status: MfaStatus = {
    enrolled: false,
    verified: false,
    required: true,
    enrollment_required: true,
    recovery_codes_remaining: 0,
    locked_until: null,
    method: null,
  };

  it("shows the enrolment secret and recovery codes once", async () => {
    const user = userEvent.setup();
    api.postJson
      .mockResolvedValueOnce({
        ok: true,
        data: {
          secret: "JBSWY3DPEHPK3PXP",
          provisioning_uri: "otpauth://totp/LOOPMESH:operator?secret=JBSWY3DPEHPK3PXP",
          message: "Scan",
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        data: {
          message: "Enrolled",
          recovery_codes: ["AAAA-BBBB", "CCCC-DDDD"],
          enrolled_at: "2026-01-01T00:00:00Z",
        },
      });
    render(<MfaPanel status={status} />);

    await user.type(screen.getByLabelText("Current password"), "CorrectHorse!1");
    await user.click(screen.getByRole("button", { name: "Begin enrolment" }));
    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Six-digit code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm enrolment" }));

    expect(await screen.findByText("AAAA-BBBB")).toBeInTheDocument();
    expect(screen.getByText(/shown once, never again/)).toBeInTheDocument();
    expect(localStorage.length).toBe(0);

    await user.click(screen.getByRole("button", { name: "I saved these codes" }));
    expect(screen.queryByText("AAAA-BBBB")).not.toBeInTheDocument();
  });

  it("keeps the platform closed on a session without a second factor", () => {
    render(
      <MfaPanel
        status={{ ...status, enrolled: true, enrollment_required: false, recovery_codes_remaining: 4 }}
      />,
    );
    expect(screen.getByText(/Platform routes stay closed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verify session" })).toBeInTheDocument();
  });
});

describe("operator sessions", () => {
  it("revokes a selected session but not the current one", async () => {
    const user = userEvent.setup();
    api.postJson.mockResolvedValue({
      ok: true,
      data: { message: "Platform operator session revoked.", revoked_count: 1 },
    });
    render(
      <OperatorSessions
        sessions={[session({ id: "current", is_current: true }), session({ id: "other" })]}
      />,
    );

    expect(screen.getAllByRole("button", { name: "Revoke this session" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Revoke this session" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm revocation" }),
    );

    expect(api.postJson).toHaveBeenCalledWith("/platform/sessions/other/revoke", {});
    expect(await screen.findByRole("status")).toHaveTextContent(/revoked/);
  });
});

describe("audit export controls", () => {
  it("explains the separate export capability", () => {
    render(
      <AuditExport
        canExport={false}
        values={{
          created_from: "",
          created_to: "",
          actor: "",
          event_type: "",
          entity_type: "",
          entity_id: "",
          target_user_id: "",
          organization_id: "",
        }}
      />,
    );
    expect(screen.getByText(/platform.audit.export/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Export/ })).not.toBeInTheDocument();
  });
});
