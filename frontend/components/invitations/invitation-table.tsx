"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { postJson } from "@/lib/client-api";
import { roleLabel } from "@/lib/auth";
import {
  type Invitation,
  invitationStatusLabel,
  isExpired,
} from "@/lib/account-types";
import { formatDate, relativeTime } from "@/lib/format";

function statusTone(status: string): string {
  if (status === "pending") return "border-forest-700/25 bg-forest-800/[0.08] text-forest-700";
  if (status === "accepted") return "border-lime-500/40 bg-lime-400/20 text-forest-800";
  if (status === "revoked") return "border-paper-300 bg-paper-200/60 text-ink-500";
  return "border-clay-500/30 bg-clay-500/10 text-clay-500";
}

/**
 * Pending invitation register.
 *
 * Revocation is an API call; the row is only marked revoked once the server
 * confirms it, so the table never shows a state the backend did not accept.
 */
export function InvitationTable({ initial }: { initial: Invitation[] }) {
  const [invitations, setInvitations] = useState<Invitation[]>(initial);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const pending = invitations.filter((row) => row.status === "pending" && !isExpired(row.expires_at));
  const history = invitations.filter((row) => !(row.status === "pending" && !isExpired(row.expires_at)));

  async function revoke(row: Invitation) {
    if (busyId) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(`Revoke the invitation for ${row.email}? The link stops working immediately.`);
    if (!confirmed) return;

    setBusyId(row.id);
    setError(null);
    setNotice(null);
    const result = await postJson<Invitation>(`/auth/invitations/${row.id}/revoke`, {});

    if (!result.ok) {
      setBusyId(null);
      setError(result.error);
      return;
    }

    setInvitations((current) =>
      current.map((item) =>
        item.id === row.id
          ? { ...item, status: result.data.status, delivery_token: null }
          : item,
      ),
    );
    setBusyId(null);
    setNotice(`Invitation for ${row.email} revoked.`);
  }

  return (
    <div>
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

      {pending.length === 0 ? (
        <EmptyState
          title="No pending invitations"
          description="Invitations you create appear here until they are accepted, expire or are revoked."
        />
      ) : (
        <ul className="divide-y divide-paper-200">
          {pending.map((row) => (
            <li key={row.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3.5 sm:px-6">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-[12.5px] font-medium text-ink-900">{row.email}</p>
                  <span className="rounded border border-paper-300 bg-paper-100 px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider text-ink-600">
                    {roleLabel(row.role)}
                  </span>
                  <span
                    className={`rounded border px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider ${statusTone(
                      isExpired(row.expires_at) ? "expired" : row.status,
                    )}`}
                  >
                    {isExpired(row.expires_at) ? "Expired" : invitationStatusLabel(row.status)}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[10px] text-ink-400">
                  Invited {relativeTime(row.created_at)} · expires {formatDate(row.expires_at)}
                  {row.note ? ` · “${row.note}”` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void revoke(row)}
                disabled={busyId === row.id}
                className="shrink-0 rounded-lg border border-rust-500/30 bg-rust-500/[0.06] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-rust-500 transition-colors hover:bg-rust-500/10 disabled:opacity-60"
              >
                {busyId === row.id ? "Revoking…" : "Revoke"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {history.length > 0 ? (
        <div className="border-t border-paper-200 px-5 py-4 sm:px-6">
          <p className="label-mono text-[8.5px] text-ink-400">Earlier invitations</p>
          <ul className="mt-2 space-y-1.5">
            {history.slice(0, 10).map((row) => (
              <li key={row.id} className="flex flex-wrap items-baseline gap-2 text-[11px] text-ink-400">
                <span className="text-ink-600">{row.email}</span>
                <span className="font-mono text-[9.5px] uppercase tracking-wider">
                  {isExpired(row.expires_at) && row.status === "pending"
                    ? "expired"
                    : invitationStatusLabel(row.status)}
                </span>
                <span className="font-mono text-[9.5px]">
                  {formatDate(row.accepted_at ?? row.expires_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
