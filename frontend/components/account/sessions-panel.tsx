"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { getJson, postJson } from "@/lib/client-api";
import type { AuthMessage } from "@/lib/auth";
import { type SessionInfo, deviceLabel } from "@/lib/account-types";
import { formatDate, relativeTime, titleCase } from "@/lib/format";

function orderSessions(sessions: SessionInfo[]): SessionInfo[] {
  return [...sessions].sort((a, b) => {
    if (a.is_current !== b.is_current) return a.is_current ? -1 : 1;
    const aActive = a.revoked_at === null ? 0 : 1;
    const bActive = b.revoked_at === null ? 0 : 1;
    if (aActive !== bActive) return aActive - bActive;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
}

/**
 * Session and device management.
 *
 * Only the API's safe projection is rendered: identifiers, timestamps and a
 * user-agent label. Access and refresh tokens are HttpOnly cookies and are
 * never part of this payload.
 */
export function SessionsPanel({ initialSessions }: { initialSessions: SessionInfo[] }) {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionInfo[]>(orderSessions(initialSessions));
  const [busyId, setBusyId] = useState<string | null>(null);
  const [busyAll, setBusyAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const active = sessions.filter((session) => session.revoked_at === null);
  const revoked = sessions.filter((session) => session.revoked_at !== null);

  async function reload() {
    const result = await getJson<SessionInfo[]>("/auth/sessions");
    if (result.ok) setSessions(orderSessions(result.data));
    else setError(result.error);
  }

  async function revoke(session: SessionInfo) {
    if (busyId || busyAll) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(
        session.is_current
          ? "Revoke this session? You will be signed out immediately."
          : `Revoke the session from ${deviceLabel(session.user_agent)}? That device will be signed out.`,
      );
    if (!confirmed) return;

    setBusyId(session.id);
    setError(null);
    setNotice(null);
    const result = await postJson<AuthMessage>(`/auth/sessions/${session.id}/revoke`, {});

    if (!result.ok) {
      setBusyId(null);
      setError(result.error);
      return;
    }

    if (result.data.authenticated === false) {
      // The current session was revoked; the API cleared the cookies.
      router.replace("/login?reason=signed_out");
      router.refresh();
      return;
    }

    setNotice("Session revoked. That device must sign in again.");
    setBusyId(null);
    await reload();
  }

  async function revokeOthers() {
    if (busyId || busyAll) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm("Revoke every session except this one? Other devices will be signed out.");
    if (!confirmed) return;

    setBusyAll(true);
    setError(null);
    setNotice(null);
    const result = await postJson<AuthMessage>("/auth/sessions/revoke-others", {});

    if (!result.ok) {
      setBusyAll(false);
      setError(result.error);
      return;
    }

    setNotice("All other sessions were revoked.");
    setBusyAll(false);
    await reload();
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-paper-200 px-5 py-4 sm:px-6">
        <div>
          <p className="label-mono text-[8.5px] text-ink-400">Active sessions</p>
          <h2 className="text-[15px] font-semibold text-ink-900">
            {active.length} signed in{active.length === 1 ? " device" : " devices"}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => void revokeOthers()}
          disabled={busyAll || active.length < 2}
          className="rounded-lg border border-paper-300 bg-paper-50 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-600 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyAll ? "Revoking…" : "Revoke other sessions"}
        </button>
      </div>

      {error ? (
        <p
          role="alert"
          className="mx-5 mt-4 rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500 sm:mx-6"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="mx-5 mt-4 rounded-lg border border-forest-700/25 bg-forest-800/[0.06] px-3 py-2.5 text-[12px] leading-relaxed text-forest-700 sm:mx-6"
        >
          {notice}
        </p>
      ) : null}

      <ul className="divide-y divide-paper-200">
        {active.map((session) => (
          <li key={session.id} className="px-5 py-4 sm:px-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[13px] font-medium text-ink-900">
                    {deviceLabel(session.user_agent)}
                  </p>
                  {session.is_current ? (
                    <span className="rounded border border-forest-700/25 bg-forest-800/[0.08] px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider text-forest-700">
                      This device
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 font-mono text-[10px] text-ink-400">
                  Started {formatDate(session.created_at)} · last seen{" "}
                  {relativeTime(session.last_seen_at ?? session.created_at)} · access expires{" "}
                  {formatDate(session.access_expires_at)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void revoke(session)}
                disabled={busyId === session.id || busyAll}
                className="shrink-0 rounded-lg border border-rust-500/30 bg-rust-500/[0.06] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-rust-500 transition-colors hover:bg-rust-500/10 disabled:opacity-60"
              >
                {busyId === session.id ? "Revoking…" : session.is_current ? "Sign out" : "Revoke"}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {revoked.length > 0 ? (
        <div className="border-t border-paper-200 px-5 py-4 sm:px-6">
          <p className="label-mono text-[8.5px] text-ink-400">Recently ended</p>
          <ul className="mt-2 space-y-1.5">
            {revoked.slice(0, 8).map((session) => (
              <li key={session.id} className="flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                <span className="text-ink-600">{deviceLabel(session.user_agent)}</span>
                <span className="font-mono text-[9.5px]">
                  {session.revoked_reason ? titleCase(session.revoked_reason) : "Revoked"} ·{" "}
                  {relativeTime(session.revoked_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
