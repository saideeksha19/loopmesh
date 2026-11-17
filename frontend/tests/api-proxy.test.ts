// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "../app/api/v1/[...path]/route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

function upstream(status: number, body: unknown, cookies: string[] = []): Response {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
  for (const cookie of cookies) response.headers.append("set-cookie", cookie);
  return response;
}

describe("same-origin API proxy", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards session cookies privately and relays the JSON body", async () => {
    const fetchMock = vi.fn(async () => upstream(200, { items: [], total: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost:3000/api/v1/materials?page=2", {
      headers: { cookie: "lm_session=abc; lm_csrf=nonce", accept: "application/json" },
    });
    const response = await GET(request, context(["materials"]));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ items: [], total: 0 });
    expect(response.headers.get("cache-control")).toBe("no-store");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/materials\?page=2$/);
    const forwarded = new Headers(init.headers);
    expect(forwarded.get("cookie")).toBe("lm_session=abc; lm_csrf=nonce");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("relays every Set-Cookie header from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        upstream(200, { authenticated: true }, [
          "lm_session=fresh; Path=/; HttpOnly; SameSite=lax",
          "lm_csrf=nonce2; Path=/; SameSite=lax",
        ]),
      ),
    );

    const request = new NextRequest("http://localhost:3000/api/v1/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json", cookie: "lm_bootstrap=1" },
      body: JSON.stringify({ email: "ada@aurelia.example", password: "secret" }),
    });
    const response = await POST(request, context(["auth", "login"]));

    expect(response.status).toBe(200);
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(response.headers.getSetCookie()[0]).toContain("lm_session=fresh");
  });

  it("passes the CSRF header through and does not forward credentials up as headers", async () => {
    const fetchMock = vi.fn(async () => upstream(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost:3000/api/v1/auth/switch-organization", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-csrf-token": "nonce",
        authorization: "Bearer should-not-leak",
        "x-actor-id": "legacy-header",
        cookie: "lm_session=abc; lm_csrf=nonce",
      },
      body: JSON.stringify({ organization_id: "org-b" }),
    });
    await POST(request, context(["auth", "switch-organization"]));

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const forwarded = new Headers(init.headers);
    expect(forwarded.get("x-csrf-token")).toBe("nonce");
    expect(forwarded.get("authorization")).toBeNull();
    expect(forwarded.get("x-actor-id")).toBeNull();
    expect(init.body).toBeDefined();
  });

  it("answers 503 when the API cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const request = new NextRequest("http://localhost:3000/api/v1/auth/me");
    const response = await GET(request, context(["auth", "me"]));

    expect(response.status).toBe(503);
    const body = (await response.json()) as { error: { code: string } };
    expect(body.error.code).toBe("api_unreachable");
  });
});
