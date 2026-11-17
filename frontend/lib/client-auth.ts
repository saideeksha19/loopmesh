"use client";

import { CSRF_COOKIE, LOGIN_PATH } from "@/lib/auth";

/**
 * Browser authentication transport.
 *
 * Every request goes to the same-origin proxy (`/api/v1/*`), which forwards the
 * cookies to the API. Credentials are never read from JavaScript storage: the
 * only cookie accessible here is the CSRF nonce.
 */

export const API_PREFIX = "/api/v1";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function withRequestHeaders(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  if (UNSAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  return { ...init, headers, credentials: "same-origin", cache: "no-store" };
}

let refreshInFlight: Promise<boolean> | null = null;

async function performRefresh(): Promise<boolean> {
  try {
    const response = await fetch(`${API_PREFIX}/auth/refresh`, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Rotate the session once, shared by every concurrent caller. A single
 * in-flight promise prevents a burst of 401s from replaying the refresh token
 * (which the API treats as theft and answers by revoking the family).
 */
export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/**
 * Fetch through the proxy. A 401 triggers at most one renewal and one replay;
 * there is no loop even if the API keeps answering 401.
 */
export async function authFetch(
  path: string,
  init: RequestInit = {},
  { retryOnExpiry = true }: { retryOnExpiry?: boolean } = {},
): Promise<Response> {
  const url = `${API_PREFIX}${path}`;
  const send = () => fetch(url, withRequestHeaders(init));

  let response = await send();
  if (response.status === 401 && retryOnExpiry) {
    const renewed = await refreshSession();
    if (renewed) response = await send();
  }
  return response;
}

/** Send the browser to sign-in, remembering the current page. */
export function redirectToLogin(reason = "session_expired"): void {
  if (typeof window === "undefined") return;
  const here = `${window.location.pathname}${window.location.search}`;
  const next = here && here !== LOGIN_PATH ? `&next=${encodeURIComponent(here)}` : "";
  window.location.assign(`${LOGIN_PATH}?reason=${reason}${next}`);
}
