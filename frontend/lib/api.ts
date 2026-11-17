/**
 * Server-side API client.
 *
 * The backend URL is read from API_INTERNAL_URL (server-only) and falls back to
 * NEXT_PUBLIC_API_URL. Requests are never cached so the workspace always shows
 * the current database state.
 *
 * Authentication is cookie based, so the incoming request's cookies are
 * forwarded to the API. Server components cannot set cookies; renewal happens
 * in route handlers (see `app/auth/resume`) and in the client session keeper.
 */

import { cookies } from "next/headers";

import { API_BASE } from "@/lib/api-base";

export { API_BASE };

export type ApiSuccess<T> = { ok: true; data: T };
export type ApiFailure = {
  ok: false;
  error: string;
  status?: number;
  code?: string;
  reason?: string;
};
export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

const TIMEOUT_MS = 6000;

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    details?: { reason?: string } & Record<string, unknown>;
  };
};

async function requestCookieHeader(): Promise<string | undefined> {
  try {
    const store = await cookies();
    const pairs = store.getAll().map((cookie) => `${cookie.name}=${cookie.value}`);
    return pairs.length > 0 ? pairs.join("; ") : undefined;
  } catch {
    // Not inside a request scope (build-time or offline tooling).
    return undefined;
  }
}

export async function apiGet<T>(path: string): Promise<ApiResult<T>> {
  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    const cookie = await requestCookieHeader();
    if (cookie) headers.cookie = cookie;

    const response = await fetch(`${API_BASE}/api/v1${path}`, {
      cache: "no-store",
      headers,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    if (!response.ok) {
      let message = `API responded with ${response.status}`;
      let code: string | undefined;
      let reason: string | undefined;
      try {
        const body = (await response.json()) as ErrorEnvelope;
        if (body?.error?.message) message = body.error.message;
        code = body?.error?.code;
        reason = body?.error?.details?.reason;
      } catch {
        /* non-JSON error body */
      }
      return { ok: false, error: message, status: response.status, code, reason };
    }

    return { ok: true, data: (await response.json()) as T };
  } catch (error) {
    const reason =
      error instanceof Error && error.name === "TimeoutError"
        ? "The API did not respond in time."
        : "The LOOPMESH API is not reachable.";
    return { ok: false, error: reason };
  }
}
