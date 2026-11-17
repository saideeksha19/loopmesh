// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "../app/api/v1/auth/resume/route";

function upstream(status: number, cookies: string[] = []): Response {
  const response = new Response(JSON.stringify({ message: "upstream" }), {
    status,
    headers: { "content-type": "application/json" },
  });
  for (const cookie of cookies) response.headers.append("set-cookie", cookie);
  return response;
}

function resumeRequest(cookie: string): NextRequest {
  return new NextRequest("http://localhost:3000/api/v1/auth/resume", {
    headers: cookie ? { cookie } : {},
  });
}

function location(response: Response): string {
  return response.headers.get("location") ?? "";
}

describe("silent session renewal", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("rotates the session and resumes the last visited page", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      upstream(200, ["lm_session=fresh; Path=/; HttpOnly", "lm_csrf=nonce; Path=/"]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      resumeRequest("lm_refresh=refresh-1; lm_last_path=%2Fmaterials%3Fpage%3D2"),
    );

    expect(response.status).toBe(303);
    expect(location(response)).toBe("http://localhost:3000/materials?page=2");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/v1\/auth\/refresh$/);
    expect(response.headers.getSetCookie()).toEqual([
      "lm_session=fresh; Path=/; HttpOnly",
      "lm_csrf=nonce; Path=/",
    ]);
  });

  it("ignores an off-site remembered path", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => upstream(200, ["lm_session=fresh; Path=/"])));

    const response = await GET(resumeRequest("lm_refresh=refresh-1; lm_last_path=%2F%2Fevil.example"));

    expect(location(response)).toBe("http://localhost:3000/overview");
  });

  it("sends an invalid refresh to sign-in and relays the cookie deletion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => upstream(401, ["lm_refresh=; Path=/api/v1/auth; Max-Age=0"])),
    );

    const response = await GET(resumeRequest("lm_refresh=stale; lm_last_path=%2Fledger"));

    expect(response.status).toBe(303);
    expect(location(response)).toBe("http://localhost:3000/login?reason=session_expired");
    expect(response.headers.getSetCookie()).toEqual(["lm_refresh=; Path=/api/v1/auth; Max-Age=0"]);
  });

  it("goes straight to sign-in when there is no refresh cookie", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(resumeRequest(""));

    expect(location(response)).toBe("http://localhost:3000/login?reason=required");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains an expiry when a lapsed session cookie is still present", async () => {
    vi.stubGlobal("fetch", vi.fn());

    const response = await GET(resumeRequest("lm_session=lapsed"));

    expect(location(response)).toBe("http://localhost:3000/login?reason=session_expired");
  });

  it("reports an unreachable API instead of looping", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    const response = await GET(resumeRequest("lm_refresh=refresh-1"));

    expect(location(response)).toBe("http://localhost:3000/login?reason=api_unavailable");
  });
});
