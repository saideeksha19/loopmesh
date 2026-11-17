import { NextRequest, NextResponse } from "next/server";

import { API_BASE } from "@/lib/api-base";
import {
  LAST_PATH_COOKIE,
  LOGIN_PATH,
  REFRESH_COOKIE,
  SESSION_COOKIE,
  safeNextPath,
} from "@/lib/auth";

/**
 * Silent renewal entry point.
 *
 * A server component cannot set cookies, so when the access cookie has lapsed
 * but the refresh cookie is still redeemable the workspace layout redirects
 * here. This handler rotates the session, relays the new cookies to the
 * browser and sends the user back to the page they were last on.
 */

export const dynamic = "force-dynamic";

const UPSTREAM_TIMEOUT_MS = 10_000;

function finish(request: NextRequest, location: string, upstream?: Response): NextResponse {
  const response = NextResponse.redirect(new URL(location, request.nextUrl.origin), 303);
  response.headers.set("cache-control", "no-store");
  if (upstream) {
    for (const cookie of upstream.headers.getSetCookie()) {
      response.headers.append("set-cookie", cookie);
    }
  }
  return response;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!request.cookies.get(REFRESH_COOKIE)) {
    const reason = request.cookies.get(SESSION_COOKIE) ? "session_expired" : "required";
    return finish(request, `${LOGIN_PATH}?reason=${reason}`);
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: {
        accept: "application/json",
        cookie: request.headers.get("cookie") ?? "",
        "user-agent": request.headers.get("user-agent") ?? "",
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return finish(request, `${LOGIN_PATH}?reason=api_unavailable`);
  }

  if (!upstream.ok) {
    // The API clears the cookies when the refresh family is invalid, expired or
    // replayed; relaying that response is what stops a renewal loop.
    return finish(request, `${LOGIN_PATH}?reason=session_expired`, upstream);
  }

  const target = safeNextPath(request.cookies.get(LAST_PATH_COOKIE)?.value);
  return finish(request, target, upstream);
}
