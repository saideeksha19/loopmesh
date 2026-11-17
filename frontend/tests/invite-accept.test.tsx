import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteAcceptForm } from "@/components/invitations/invite-accept-form";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

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

const ACCEPTED = {
  message: "Invitation accepted.",
  authenticated: true,
  user: { id: "u1", email: "new@example.com", full_name: "New Member", must_change_password: false },
};

async function fill(values: { name: string; password: string; confirm: string }) {
  const user = userEvent.setup();
  if (values.name) await user.type(screen.getByLabelText("Full name"), values.name);
  if (values.password) await user.type(screen.getByLabelText("Choose a password"), values.password);
  if (values.confirm) await user.type(screen.getByLabelText("Repeat password"), values.confirm);
  await user.click(screen.getByRole("button", { name: "Accept invitation" }));
}

function renderForm() {
  return render(
    <InviteAcceptForm token="tok-abc123" email="new@example.com" organizationName="Aurelia Works" />,
  );
}

describe("invitation acceptance form", () => {
  beforeEach(() => {
    router.replace.mockReset();
    router.refresh.mockReset();
  });

  it("names the organisation and invited address without exposing the token", () => {
    mockFetch(() => jsonResponse(200, ACCEPTED));
    renderForm();

    expect(screen.getByText("Aurelia Works")).toBeInTheDocument();
    expect(screen.getByText("new@example.com")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("tok-abc123");
  });

  it("refuses a password that fails the policy before calling the API", async () => {
    const calls = mockFetch(() => jsonResponse(200, ACCEPTED));
    renderForm();

    await fill({ name: "New Member", password: "short", confirm: "short" });

    expect(screen.getByText(/Password needs:/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("refuses a mismatched confirmation", async () => {
    const calls = mockFetch(() => jsonResponse(200, ACCEPTED));
    renderForm();

    await fill({ name: "New Member", password: "StrongPass!2345", confirm: "StrongPass!23456" });

    expect(screen.getByText("The passwords do not match.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("accepts the invitation and opens the workspace", async () => {
    const calls = mockFetch(() => jsonResponse(200, ACCEPTED));
    renderForm();

    await fill({ name: "  New Member  ", password: "StrongPass!2345", confirm: "StrongPass!2345" });

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/auth/invitations/accept");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      token: "tok-abc123",
      full_name: "New Member",
      password: "StrongPass!2345",
    });
  });

  it("reports a token that has expired, been used or been revoked", async () => {
    mockFetch(() =>
      jsonResponse(401, {
        error: {
          code: "authentication_error",
          message: "Invitation is invalid or has expired.",
          details: { reason: "invalid_invitation" },
        },
      }),
    );
    renderForm();

    await fill({ name: "New Member", password: "StrongPass!2345", confirm: "StrongPass!2345" });

    expect(await screen.findByRole("alert")).toHaveTextContent("can no longer be used");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("keeps the API's wording when the address already has an account", async () => {
    mockFetch(() =>
      jsonResponse(401, {
        error: {
          code: "authentication_error",
          message: "Invitation acceptance requires your current account password.",
          details: { reason: "invalid_credentials" },
        },
      }),
    );
    renderForm();

    await fill({ name: "Existing Person", password: "StrongPass!2345", confirm: "StrongPass!2345" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invitation acceptance requires your current account password.",
    );
    expect(screen.queryByText("can no longer be used")).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });
});
