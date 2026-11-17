import { cache } from "react";
import { redirect } from "next/navigation";

import { apiGet } from "@/lib/api";
import { sessionRedirectTarget, type SessionUser } from "@/lib/auth";

export type SessionState =
  | { status: "authenticated"; user: SessionUser }
  | { status: "anonymous" }
  | { status: "unavailable"; error: string };

/**
 * Resolve the current principal for the duration of one request.
 *
 * `cache` keeps the layout and any page that needs the same facts to a single
 * `/auth/me` call. A 401 is the only "not signed in" signal; transport errors
 * are surfaced separately so an offline API never looks like a sign-out.
 */
export const loadSession = cache(async (): Promise<SessionState> => {
  const result = await apiGet<SessionUser>("/auth/me");
  if (result.ok) return { status: "authenticated", user: result.data };
  if (result.status === 401) return { status: "anonymous" };
  return { status: "unavailable", error: result.error };
});

/** Send an unauthenticated request to renewal, then sign-in if needed. */
export async function redirectToSignIn(): Promise<never> {
  redirect(sessionRedirectTarget());
}
