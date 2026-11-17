"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";

import { LAST_PATH_COOKIE, type SessionUser } from "@/lib/auth";
import { API_PREFIX, redirectToLogin, refreshSession } from "@/lib/client-auth";

const CHECK_MARGIN_MS = 90_000;
const FALLBACK_POLL_MS = 5 * 60_000;
const MIN_DELAY_MS = 5_000;

function fetchMe(): Promise<Response> {
  return fetch(`${API_PREFIX}/auth/me`, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
}

/**
 * Keeps the browser session alive without ever holding a credential in JS.
 *
 * - rotates the refresh cookie shortly before the access cookie lapses
 * - re-validates when the tab becomes visible again or the network returns
 * - sends the user to sign-in when the session is revoked or unrecoverable
 *
 * Every renewal goes through `refreshSession`, whose single-flight promise
 * makes concurrent checks share one rotation, so a refresh token can never be
 * replayed by the UI itself.
 */
export function SessionKeeper({ expiresAt }: { expiresAt: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const expiryRef = useRef<number | null>(expiresAt ? Date.parse(expiresAt) : null);

  // Remember where the user was, so a silent renewal can return them there.
  useEffect(() => {
    if (!pathname) return;
    document.cookie = `${LAST_PATH_COOKIE}=${encodeURIComponent(pathname)}; path=/; max-age=86400; samesite=lax`;
  }, [pathname]);

  useEffect(() => {
    let cancelled = false;
    let running = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    function armDelay(delay: number) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void sync(), Math.max(MIN_DELAY_MS, delay));
    }

    function arm(at: number | null) {
      armDelay(at === null ? FALLBACK_POLL_MS : at - Date.now() - CHECK_MARGIN_MS);
    }

    async function sync(): Promise<void> {
      if (running || cancelled) return;
      running = true;
      let rotated = false;
      try {
        for (let attempt = 0; attempt < 2; attempt += 1) {
          const expires = expiryRef.current;
          const due = expires === null || expires - Date.now() <= CHECK_MARGIN_MS;
          if (attempt === 0 && due) {
            rotated = (await refreshSession()) || rotated;
            if (cancelled) return;
          }

          let response: Response;
          try {
            response = await fetchMe();
          } catch {
            // Network interruption: keep the current screen, try again later.
            armDelay(60_000);
            return;
          }
          if (cancelled) return;

          if (response.status === 401) {
            if (attempt === 1) {
              redirectToLogin("session_revoked");
              return;
            }
            const renewed = await refreshSession();
            if (cancelled) return;
            if (!renewed) {
              redirectToLogin("session_expired");
              return;
            }
            rotated = true;
            continue;
          }

          if (!response.ok) {
            armDelay(60_000);
            return;
          }

          const user = (await response.json()) as SessionUser;
          expiryRef.current = user.session_expires_at ? Date.parse(user.session_expires_at) : null;
          if (rotated) router.refresh();
          arm(expiryRef.current);
          return;
        }
      } finally {
        running = false;
      }
    }

    function onVisible() {
      if (document.visibilityState === "visible") void sync();
    }

    arm(expiryRef.current);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    window.addEventListener("focus", onVisible);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [router]);

  return null;
}
