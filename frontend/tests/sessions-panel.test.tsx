import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionsPanel } from "@/components/account/sessions-panel";
import type { SessionInfo } from "@/lib/account-types";

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

function session(overrides: Partial<SessionInfo> = {}): SessionInfo {
  return {
    id: "sess-current",
    organization_id: "org-1",
    created_at: "2026-11-15T09:00:00Z",
    last_seen_at: "2026-11-15T10:00:00Z",
    access_expires_at: "2026-11-15T11:00:00Z",
    refresh_expires_at: "2026-11-22T09:00:00Z",
    revoked_at: null,
    revoked_reason: null,
    is_current: true,
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
    ...overrides,
  };
}

const OTHER = session({
  id: "sess-other",
  is_current: false,
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Firefox/121.0",
});

describe("session management panel", () => {
  beforeEach(() => {
    router.replace.mockReset();
    router.refresh.mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("identifies the current device and never renders credentials", () => {
    mockFetch(() => jsonResponse(200, [session(), OTHER]));
    render(<SessionsPanel initialSessions={[session(), OTHER]} />);

    expect(screen.getByText("Chrome on Windows")).toBeInTheDocument();
    expect(screen.getByText("Firefox on macOS")).toBeInTheDocument();
    expect(screen.getByText("This device")).toBeInTheDocument();
    expect(screen.getByText("2 signed in devices")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/token/i);
  });

  it("revokes another device and refreshes the list from the API", async () => {
    const user = userEvent.setup();
    const revokedOther = {
      ...OTHER,
      revoked_at: "2026-11-15T10:05:00Z",
      revoked_reason: "user_revoked",
    };
    const calls = mockFetch((url) => {
      if (url.endsWith("/auth/sessions")) return jsonResponse(200, [session(), revokedOther]);
      return jsonResponse(200, { message: "Session revoked.", authenticated: true });
    });
    render(<SessionsPanel initialSessions={[session(), OTHER]} />);

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() =>
      expect(screen.getByText("Session revoked. That device must sign in again.")).toBeInTheDocument(),
    );
    expect(calls[0].url).toBe("/api/v1/auth/sessions/sess-other/revoke");
    expect(calls[1].url).toBe("/api/v1/auth/sessions");
    expect(screen.getByText("Recently ended")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it("signs out when the current session is revoked", async () => {
    const user = userEvent.setup();
    mockFetch(() =>
      jsonResponse(200, { message: "Current session revoked.", authenticated: false }),
    );
    render(<SessionsPanel initialSessions={[session(), OTHER]} />);

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?reason=signed_out"));
  });

  it("revokes every other session without closing the current one", async () => {
    const user = userEvent.setup();
    const calls = mockFetch((url) => {
      if (url.endsWith("/revoke-others")) {
        return jsonResponse(200, { message: "Other sessions revoked.", authenticated: true });
      }
      return jsonResponse(200, [
        session(),
        { ...OTHER, revoked_at: "2026-11-15T10:05:00Z", revoked_reason: "revoked_other_sessions" },
      ]);
    });
    render(<SessionsPanel initialSessions={[session(), OTHER]} />);

    await user.click(screen.getByRole("button", { name: "Revoke other sessions" }));

    await waitFor(() =>
      expect(screen.getByText("All other sessions were revoked.")).toBeInTheDocument(),
    );
    expect(calls[0].url).toBe("/api/v1/auth/sessions/revoke-others");
    expect(screen.getByText("1 signed in device")).toBeInTheDocument();
  });

  it("disables the bulk action when this is the only session", () => {
    mockFetch(() => jsonResponse(200, [session()]));
    render(<SessionsPanel initialSessions={[session()]} />);

    expect(screen.getByRole("button", { name: "Revoke other sessions" })).toBeDisabled();
  });

  it("does nothing when revocation is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const calls = mockFetch(() => jsonResponse(200, { authenticated: true }));
    render(<SessionsPanel initialSessions={[session(), OTHER]} />);

    await user.click(screen.getByRole("button", { name: "Revoke" }));

    expect(calls).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument();
  });
});
