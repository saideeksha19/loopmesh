"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { roleLabel } from "@/lib/auth";
import { patchJson, postJson } from "@/lib/client-api";
import {
  MEMBER_ROLE_VALUES,
  type Member,
  type MemberAction,
  type MemberResetResult,
  membershipStatusLabel,
  scopeLabel,
} from "@/lib/account-types";
import { formatDate } from "@/lib/format";

const STATUS_FILTERS = ["all", "active", "invited", "suspended", "removed"] as const;

function statusTone(status: string): string {
  if (status === "active") return "border-lime-500/40 bg-lime-400/20 text-forest-800";
  if (status === "invited") return "border-forest-700/25 bg-forest-800/[0.08] text-forest-700";
  if (status === "suspended") return "border-clay-500/30 bg-clay-500/10 text-clay-500";
  return "border-paper-300 bg-paper-200/60 text-ink-500";
}

function roleTone(role: string): string {
  if (role === "org_admin") return "border-forest-700/30 bg-forest-800/[0.08] text-forest-800";
  return "border-paper-300 bg-paper-100 text-ink-600";
}

/**
 * Organisation member register.
 *
 * The roster is read-only unless the caller holds `member.manage`; even then
 * every action is an API call whose result replaces the local row, so the table
 * never shows a state the backend did not accept. Nothing here is an
 * authorization decision — the API re-checks capability, tenant scope and the
 * last-administrator rule on every request.
 */
export function MemberRoster({
  initial,
  canManage,
}: {
  initial: Member[];
  canManage: boolean;
}) {
  const [members, setMembers] = useState<Member[]>(initial);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [draftRole, setDraftRole] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return members.filter((member) => {
      if (statusFilter !== "all" && member.status !== statusFilter) return false;
      if (!needle) return true;
      return (
        member.full_name.toLowerCase().includes(needle) ||
        member.email.toLowerCase().includes(needle) ||
        roleLabel(member.role).toLowerCase().includes(needle)
      );
    });
  }, [members, query, statusFilter]);

  function replaceMember(updated: Member) {
    setMembers((current) =>
      current.map((member) => (member.id === updated.id ? { ...member, ...updated } : member)),
    );
    setDraftRole((current) => {
      const next = { ...current };
      delete next[updated.id];
      return next;
    });
  }

  async function saveRole(member: Member) {
    const role = draftRole[member.id] ?? member.role;
    if (busyId || role === member.role) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(
        `Change ${member.full_name}'s role from ${roleLabel(member.role)} to ${roleLabel(role)}? ` +
          "The new role applies to their next request.",
      );
    if (!confirmed) {
      // Drop the unconfirmed draft so the select keeps showing the stored role.
      setDraftRole((current) => {
        const next = { ...current };
        delete next[member.id];
        return next;
      });
      return;
    }

    setBusyId(member.id);
    setError(null);
    setNotice(null);
    const result = await patchJson<Member>(`/organizations/members/${member.id}`, { role });
    setBusyId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    replaceMember(result.data);
    setNotice(`${result.data.full_name} is now ${roleLabel(result.data.role)}.`);
  }

  async function deactivate(member: Member) {
    if (busyId) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(
        `Deactivate ${member.full_name}? Their sessions opened for this organisation are ` +
          "revoked immediately and this membership grants no access. Their account and any " +
          "memberships in other organisations are not affected.",
      );
    if (!confirmed) return;

    setBusyId(member.id);
    setError(null);
    setNotice(null);
    const result = await postJson<MemberAction>(
      `/organizations/members/${member.id}/deactivate`,
      {},
    );
    setBusyId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    replaceMember(result.data.member);
    setNotice(
      `${result.data.member.full_name} deactivated. ${result.data.sessions_revoked} session(s) revoked.`,
    );
  }

  async function reactivate(member: Member) {
    if (busyId) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(
        `Reactivate ${member.full_name}? They regain ${roleLabel(member.role)} access to this ` +
          "organisation at their next sign-in.",
      );
    if (!confirmed) return;

    setBusyId(member.id);
    setError(null);
    setNotice(null);
    const result = await postJson<MemberAction>(
      `/organizations/members/${member.id}/reactivate`,
      {},
    );
    setBusyId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    replaceMember(result.data.member);
    setNotice(`${result.data.member.full_name} reactivated.`);
  }

  async function resetPassword(member: Member) {
    if (busyId) return;
    const confirmed =
      typeof window === "undefined" ||
      window.confirm(
        `Issue a password reset for ${member.full_name}? All of their sessions are revoked and ` +
          "they must set a new password before entering the workspace. No password is created, " +
          "shown or emailed.",
      );
    if (!confirmed) return;

    setBusyId(member.id);
    setError(null);
    setNotice(null);
    const result = await postJson<MemberResetResult>(
      `/organizations/members/${member.id}/reset-password`,
      {},
    );
    setBusyId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    replaceMember(result.data.member);
    setNotice(
      `${result.data.member.full_name}: password reset issued. ${result.data.sessions_revoked} session(s) revoked.`,
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 border-b border-paper-200 px-5 py-4 sm:px-6">
        <label className="min-w-0 flex-1">
          <span className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-ink-400">
            Search
          </span>
          <input
            type="search"
            aria-label="Search members"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name, email or role"
            className="w-full rounded-lg border border-paper-300 bg-white px-3 py-2 text-[12.5px] text-ink-900 outline-none focus:border-forest-700/40"
          />
        </label>
        <label>
          <span className="mb-1 block font-mono text-[9px] uppercase tracking-wider text-ink-400">
            Status
          </span>
          <select
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-lg border border-paper-300 bg-white px-3 py-2 text-[12.5px] text-ink-900 outline-none focus:border-forest-700/40"
          >
            {STATUS_FILTERS.map((status) => (
              <option key={status} value={status}>
                {status === "all" ? "All statuses" : membershipStatusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <p className="ml-auto font-mono text-[10px] uppercase tracking-wider text-ink-400">
          {visible.length} of {members.length}
        </p>
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

      {members.length === 0 ? (
        <EmptyState
          title="No members yet"
          description="Invite a colleague below. Accepted invitations appear here as active memberships."
        />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No members match"
          description="Adjust the search term or status filter to see the rest of the register."
        />
      ) : (
        <ul className="divide-y divide-paper-200">
          {visible.map((member) => {
            const pendingRole = draftRole[member.id] ?? member.role;
            const roleChanged = pendingRole !== member.role;
            const busy = busyId === member.id;
            return (
              <li key={member.id} className="px-5 py-4 sm:px-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-[12.5px] font-medium text-ink-900">
                        {member.full_name || member.email}
                      </p>
                      {member.is_self ? (
                        <span className="rounded border border-forest-700/25 bg-forest-800/[0.08] px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider text-forest-700">
                          You
                        </span>
                      ) : null}
                      <span
                        className={`rounded border px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider ${roleTone(
                          member.role,
                        )}`}
                      >
                        {roleLabel(member.role)}
                      </span>
                      <span
                        className={`rounded border px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider ${statusTone(
                          member.status,
                        )}`}
                      >
                        {membershipStatusLabel(member.status)}
                      </span>
                      {member.scope === "platform" ? (
                        <span className="rounded border border-clay-500/30 bg-clay-500/10 px-1.5 py-[2px] font-mono text-[9px] uppercase tracking-wider text-clay-500">
                          {scopeLabel(member.scope)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 truncate font-mono text-[10px] text-ink-400">
                      {member.email} · joined {formatDate(member.joined_at)}
                    </p>
                  </div>

                  {canManage && !member.is_self ? (
                    <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                      <select
                        aria-label={`Role for ${member.email}`}
                        value={pendingRole}
                        disabled={busy}
                        onChange={(event) =>
                          setDraftRole((current) => ({
                            ...current,
                            [member.id]: event.target.value,
                          }))
                        }
                        className="rounded-lg border border-paper-300 bg-white px-2 py-1.5 text-[11.5px] text-ink-800 outline-none focus:border-forest-700/40 disabled:opacity-60"
                      >
                        {MEMBER_ROLE_VALUES.map((role) => (
                          <option key={role} value={role}>
                            {roleLabel(role)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() => void saveRole(member)}
                        disabled={busy || !roleChanged}
                        className="rounded-lg border border-forest-700/25 bg-forest-800/[0.06] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-forest-700 transition-colors hover:bg-forest-800/10 disabled:opacity-40"
                      >
                        {busy ? "Saving…" : "Save role"}
                      </button>
                      {member.status === "suspended" ? (
                        <button
                          type="button"
                          onClick={() => void reactivate(member)}
                          disabled={busy}
                          className="rounded-lg border border-forest-700/25 bg-forest-800/[0.06] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-forest-700 transition-colors hover:bg-forest-800/10 disabled:opacity-60"
                        >
                          Reactivate
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void deactivate(member)}
                          disabled={busy || member.status !== "active"}
                          className="rounded-lg border border-clay-500/30 bg-clay-500/[0.06] px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-clay-500 transition-colors hover:bg-clay-500/10 disabled:opacity-40"
                        >
                          Deactivate
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => void resetPassword(member)}
                        disabled={busy}
                        className="rounded-lg border border-paper-300 bg-paper-100 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-600 transition-colors hover:bg-paper-200 disabled:opacity-60"
                      >
                        Reset password
                      </button>
                    </div>
                  ) : null}
                </div>
                {!canManage ? null : member.is_self ? (
                  <p className="mt-2 text-[11px] leading-relaxed text-ink-400">
                    Your own membership is managed by another administrator. The API refuses
                    self-changes so an organisation cannot lose its last administrator.
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
