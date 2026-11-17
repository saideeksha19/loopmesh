import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PasswordForm } from "@/components/account/password-form";

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

async function fill(values: { current?: string; next?: string; confirm?: string }) {
  const user = userEvent.setup();
  if (values.current) await user.type(screen.getByLabelText("Current password"), values.current);
  if (values.next) await user.type(screen.getByLabelText("New password"), values.next);
  if (values.confirm) await user.type(screen.getByLabelText("Repeat new password"), values.confirm);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

describe("password change form", () => {
  beforeEach(() => {
    router.replace.mockReset();
    router.refresh.mockReset();
  });

  it("explains the lock when a rotation is outstanding", () => {
    mockFetch(() => jsonResponse(200, {}));
    render(<PasswordForm required />);

    expect(screen.getByRole("status")).toHaveTextContent(/Set your own password to open the workspace/);
  });

  it("does not show the lock notice for an ordinary change", () => {
    mockFetch(() => jsonResponse(200, {}));
    render(<PasswordForm required={false} />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("rejects a weak new password locally", async () => {
    const calls = mockFetch(() => jsonResponse(200, {}));
    render(<PasswordForm required />);

    await fill({ current: "InitialPass!2345", next: "alllowercasepass", confirm: "alllowercasepass" });

    expect(screen.getByText(/Password needs:/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("rejects reusing the current password", async () => {
    const calls = mockFetch(() => jsonResponse(200, {}));
    render(<PasswordForm required={false} />);

    await fill({
      current: "StrongPass!2345",
      next: "StrongPass!2345",
      confirm: "StrongPass!2345",
    });

    expect(screen.getByText("Choose a password you have not used here before.")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("reports a wrong current password and clears the field", async () => {
    mockFetch(() =>
      jsonResponse(401, {
        error: {
          code: "authentication_error",
          message: "Current password is incorrect.",
          details: { field: "current_password" },
        },
      }),
    );
    render(<PasswordForm required />);

    await fill({ current: "WrongPass!2345", next: "RotatedPass!6789", confirm: "RotatedPass!6789" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect.");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("Current password")).toHaveFocus();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("surfaces a stricter server-side policy instead of assuming success", async () => {
    // The browser mirror is convenience only; the server's answer always wins.
    mockFetch(() =>
      jsonResponse(422, {
        error: {
          code: "weak_password",
          message: "Password must not contain your email address.",
          details: { field: "password" },
        },
      }),
    );
    render(<PasswordForm required />);

    await fill({ current: "InitialPass!2345", next: "RotatedPass!6789", confirm: "RotatedPass!6789" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password must not contain your email address.",
    );
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("signs out to the login page after a successful change", async () => {
    const calls = mockFetch(() =>
      jsonResponse(200, { message: "Password changed. Sign in again.", authenticated: false }),
    );
    render(<PasswordForm required />);

    await fill({ current: "InitialPass!2345", next: "RotatedPass!6789", confirm: "RotatedPass!6789" });

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?reason=password_changed"));
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("/api/v1/auth/change-password");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      current_password: "InitialPass!2345",
      new_password: "RotatedPass!6789",
    });
  });
});
