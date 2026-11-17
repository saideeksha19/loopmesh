"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { postJson } from "@/lib/client-api";
import { formatDate, relativeTime } from "@/lib/format";
import type { PlatformOperatorSession } from "@/lib/platform-types";

type Target = { kind: "one"; session: PlatformOperatorSession } | { kind: "all" } | null;

/**
 * Operator session inventory. IP addresses and device fingerprints are not
 * displayed because the API does not collect them for this screen. The current
 * session has no revoke control: ending it is sign-out's job.
 */
export function OperatorSessions({ sessions }: { sessions: PlatformOperatorSession[] }) {
  const router = useRouter();
  const [target, setTarget] = useState<Target>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const active = sessions.filter((session) => !session.revoked_at);
  const revoked = sessions.filter((session) => session.revoked_at);

  async function revoke() {
    if (!target || pending) return;
    setPending(true);
    setError(null);
    const path =
      target.kind === "all"
        ? "/platform/sessions/revoke-all"
        : `/platform/sessions/${target.session.id}/revoke`;
    const result = await postJson<{ message: string; revoked_count: number }>(path, {});
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMessage(result.data.message);
    setTarget(null);
    router.refresh();
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="outline" mono>
          {active.length} active operator session{active.length === 1 ? "" : "s"}
        </Badge>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setTarget({ kind: "all" });
          }}
          disabled={active.length <= 1}
          className="h-8 rounded-lg border border-rust-500/30 bg-rust-500/10 px-3 text-[11px] text-rust-500 hover:bg-rust-500/15 disabled:opacity-50"
        >
          Revoke all other operator sessions
        </button>
      </div>

      <ul role="list" className="divide-y divide-paper-200 rounded-lg border border-paper-200">
        {sessions.map((session) => (
          <li key={session.id} className="px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 truncate text-[11.5px] font-medium text-ink-800">
                {session.user_email}
              </span>
              {session.is_current ? (
                <Badge tone="forest" mono>
                  current
                </Badge>
              ) : null}
              {session.revoked_at ? (
                <Badge tone="muted" mono>
                  revoked
                </Badge>
              ) : session.mfa_verified_at ? (
                <Badge tone="outline" mono>
                  MFA verified
                </Badge>
              ) : (
                <Badge tone="warning" mono>
                  unverified
                </Badge>
              )}
              <span className="ml-auto font-mono text-[9px] whitespace-nowrap text-ink-300">
                seen {relativeTime(session.last_seen_at)}
              </span>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-ink-300">
              {session.id.slice(0, 8)} · created {formatDate(session.created_at)} · expires by
              policy
              {session.revoked_reason ? ` · ${session.revoked_reason}` : ""}
            </p>
            {!session.revoked_at && !session.is_current ? (
              <button
                type="button"
                onClick={() => {
                  setError(null);
                  setTarget({ kind: "one", session });
                }}
                className="mt-1.5 h-7 rounded-lg border border-paper-300 px-2.5 text-[10.5px] text-ink-600 hover:bg-paper-100"
              >
                Revoke this session
              </button>
            ) : null}
          </li>
        ))}
      </ul>

      <p className="text-[10px] leading-relaxed text-ink-400">
        Revoked sessions are refused by the API on their next request, and platform privilege
        removed from an account stops working regardless of its sessions. Idle and absolute limits
        are deployment settings; the current session is kept during a bulk revocation so the
        operator can finish the action and sign out deliberately.
      </p>
      {revoked.length > 0 ? (
        <p className="text-[10px] text-ink-400">
          {revoked.length} revoked session{revoked.length === 1 ? "" : "s"} retained for audit.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="text-[11.5px] text-forest-700">
          {message}
        </p>
      ) : null}

      <Modal
        open={target !== null}
        onClose={() => {
          if (pending) return;
          setTarget(null);
          setError(null);
        }}
        title={target?.kind === "all" ? "Revoke every other operator session?" : "Revoke this session?"}
        description={
          target?.kind === "all"
            ? "Every other platform operator session is revoked immediately. The session you are using is kept. Operators must sign in again."
            : "The selected session is refused on its next request. Its owner must sign in again and present a second factor."
        }
        footer={
          <>
            <button
              type="button"
              onClick={() => setTarget(null)}
              disabled={pending}
              className="h-9 rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={revoke}
              disabled={pending}
              className="h-9 rounded-lg bg-rust-500 px-3.5 text-[12px] font-medium text-paper-50 hover:bg-rust-500/90 disabled:opacity-50"
            >
              {pending ? "Revoking…" : "Confirm revocation"}
            </button>
          </>
        }
      >
        <p className="text-[11.5px] leading-relaxed text-ink-600">
          {target?.kind === "one"
            ? `${target.session.user_email} · session ${target.session.id.slice(0, 8)}`
            : "This does not change any operator's platform flag or capabilities; it ends sessions. Privilege changes are enforced separately."}
        </p>
      </Modal>
    </div>
  );
}
