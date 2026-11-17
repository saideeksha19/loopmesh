import { beforeEach, describe, expect, it, vi } from "vitest";

import { authFetch, redirectToLogin, refreshSession } from "@/lib/client-auth";

type Call = { url: string; init: RequestInit };

function response(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function headerOf(init: RequestInit, name: string): string | null {
  return new Headers(init.headers).get(name);
}

describe("browser auth transport", () => {
  let calls: Call[];

  beforeEach(() => {
    calls = [];
    document.cookie = "lm_csrf=csrf-nonce-123; path=/";
  });

  it("attaches the CSRF nonce to unsafe requests and leaves GET alone", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
        calls.push({ url: String(input), init });
        return response(200, { ok: true });
      }),
    );

    await authFetch("/materials", { method: "POST", body: "{}" });
    await authFetch("/materials");

    expect(headerOf(calls[0].init, "X-CSRF-Token")).toBe("csrf-nonce-123");
    expect(headerOf(calls[1].init, "X-CSRF-Token")).toBeNull();
    expect(calls[0].init.credentials).toBe("same-origin");
  });

  it("renews once on 401 and replays the original request", async () => {
    let refreshed = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        calls.push({ url, init: {} });
        if (url === "/api/v1/auth/refresh") {
          refreshed = true;
          return response(200, { message: "Session refreshed." });
        }
        return refreshed ? response(200, { items: [] }) : response(401, { error: { code: "unauthorized" } });
      }),
    );

    const result = await authFetch("/proposals");

    expect(result.status).toBe(200);
    expect(calls.map((call) => call.url)).toEqual([
      "/api/v1/proposals",
      "/api/v1/auth/refresh",
      "/api/v1/proposals",
    ]);
  });

  it("stops after one renewal attempt when the refresh is refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        calls.push({ url, init: {} });
        if (url === "/api/v1/auth/refresh") return response(401, { error: { code: "unauthorized" } });
        return response(401, { error: { code: "session_expired" } });
      }),
    );

    const result = await authFetch("/ledger");

    expect(result.status).toBe(401);
    expect(calls).toHaveLength(2);
    expect(calls.map((call) => call.url)).toEqual([
      "/api/v1/ledger",
      "/api/v1/auth/refresh",
    ]);
  });

  it("shares a single refresh across concurrent 401s", async () => {
    let refreshed = false;
    let refreshCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        calls.push({ url, init: {} });
        if (url === "/api/v1/auth/refresh") {
          refreshCount += 1;
          await new Promise((resolve) => setTimeout(resolve, 10));
          refreshed = true;
          return response(200, {});
        }
        return refreshed ? response(200, {}) : response(401, {});
      }),
    );

    const [first, second] = await Promise.all([authFetch("/materials"), authFetch("/network")]);

    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(refreshCount).toBe(1);
  });

  it("refreshSession resolves false instead of throwing when the API is down", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(refreshSession()).resolves.toBe(false);
  });

  it("sends the user to sign-in with the current page remembered", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", {
      pathname: "/proposals/abc",
      search: "?tab=history",
      assign,
    });

    redirectToLogin("session_expired");

    expect(assign).toHaveBeenCalledWith(
      "/login?reason=session_expired&next=%2Fproposals%2Fabc%3Ftab%3Dhistory",
    );
  });
});
