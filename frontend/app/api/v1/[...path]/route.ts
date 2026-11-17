import { NextRequest } from "next/server";

import { API_BASE } from "@/lib/api-base";

/**
 * Same-origin API proxy.
 *
 * The API sets `SameSite=Lax` HttpOnly cookies. A browser on the Next origin
 * cannot attach those to the API origin (different site), and relaxing them to
 * `SameSite=None` would weaken CSRF posture. Proxying `/api/v1/*` through this
 * route keeps the cookies first-party, keeps CORS out of the browser entirely
 * and still lets the API perform its own double-submit CSRF validation.
 *
 * The handler is a thin transport: it copies the browser's cookies and CSRF
 * header to the API, relays the response body and all `Set-Cookie` headers
 * back, and adds nothing the API did not decide.
 */

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "accept-encoding",
]);

/** Only transport-safe, non-credential headers are forwarded upstream. */
const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "x-csrf-token",
  "user-agent",
  "accept-language",
];

const UPSTREAM_TIMEOUT_MS = 30_000;

function upstreamUrl(path: string[], search: string): string {
  const suffix = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${API_BASE}/api/v1/${suffix}${search}`;
}

async function forward(request: NextRequest, path: string[]): Promise<Response> {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const method = request.method.toUpperCase();
  const hasBody = !["GET", "HEAD"].includes(method);
  let body: ArrayBuffer | undefined;
  if (hasBody) {
    try {
      body = await request.arrayBuffer();
    } catch {
      body = new ArrayBuffer(0);
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl(path, request.nextUrl.search), {
      method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return Response.json(
      {
        error: {
          code: timedOut ? "api_timeout" : "api_unreachable",
          message: timedOut
            ? "The LOOPMESH API did not respond in time."
            : "The LOOPMESH API is not reachable.",
        },
      },
      { status: timedOut ? 504 : 503, headers: { "cache-control": "no-store" } },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === "set-cookie" || HOP_BY_HOP.has(lower)) return;
    responseHeaders.set(key, value);
  });

  // Multiple cookies arrive as separate headers; `Headers.set` would collapse
  // them into one unusable value.
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }
  responseHeaders.set("cache-control", "no-store");

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function handler(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  return forward(request, path);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const HEAD = handler;
export const OPTIONS = handler;

export const dynamic = "force-dynamic";
