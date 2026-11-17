"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import type {
  ApprovalAction,
  PlatformApproval,
  PlatformOrganizationRow,
} from "@/lib/platform-types";

const MIN_REASON = 8;

/**
 * Creates a request; it never changes the tenant. A second operator with
 * `platform.approvals.decide` must approve it, and execution is a separate
 * confirmed action on the request detail screen.
 */
export function ApprovalRequestForm({
  organizations,
  canRequest,
}: {
  organizations: PlatformOrganizationRow[];
  canRequest: boolean;
}) {
  const router = useRouter();
  const [organizationId, setOrganizationId] = useState("");
  const [action, setAction] = useState<ApprovalAction>("suspend");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PlatformApproval | null>(null);

  const selected = organizations.find((row) => row.id === organizationId);
  const reasonTooShort = action === "suspend" && reason.trim().length < MIN_REASON;

  async function submit() {
    if (!canRequest || !organizationId || reasonTooShort || pending) return;
    setPending(true);
    setError(null);
    const result = await postJson<PlatformApproval>("/platform/approvals", {
      organization_id: organizationId,
      action,
      reason: reason.trim() || null,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setCreated(result.data);
    setOrganizationId("");
    setReason("");
    router.refresh();
  }

  if (!canRequest) {
    return (
      <p className="px-4 py-4 text-[11.5px] leading-relaxed text-ink-500 sm:px-6">
        Your platform role can read requests but cannot create one. Creating a request needs
        <code className="mx-1 font-mono text-[10px]">platform.approvals.request</code>
        and the tenant lifecycle capability.
      </p>
    );
  }

  return (
    <div className="px-4 py-4 sm:px-6">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Organisation</span>
          <select
            value={organizationId}
            onChange={(event) => setOrganizationId(event.target.value)}
            className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
          >
            <option value="">Select an organisation</option>
            {organizations.map((organisation) => (
              <option key={organisation.id} value={organisation.id}>
                {organisation.name} · {organisation.status}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Requested action</span>
          <select
            value={action}
            onChange={(event) => setAction(event.target.value as ApprovalAction)}
            className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
          >
            <option value="suspend">Suspend organisation</option>
            <option value="reactivate">Reactivate organisation</option>
          </select>
        </label>
      </div>

      <label className="mt-3 block">
        <span className="label-mono text-[8.5px] text-ink-400">
          Reason {action === "suspend" ? `(required, at least ${MIN_REASON} characters)` : "(optional)"}
        </span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          maxLength={400}
          className="mt-1 w-full rounded-lg border border-paper-300 bg-paper-50 p-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
        />
      </label>
      <p className="mt-1 font-mono text-[9.5px] text-ink-400">{reason.trim().length}/400</p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={pending || !organizationId || reasonTooShort}
          className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 transition-colors hover:bg-forest-800 disabled:opacity-50"
        >
          {pending ? "Creating request…" : "Request approval"}
        </button>
        {selected && selected.status !== (action === "suspend" ? "active" : "suspended") ? (
          <p className="text-[10.5px] text-ink-400">
            {selected.name} is currently {selected.status}; the API refuses an impossible transition.
          </p>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}
      {created ? (
        <p role="status" className="mt-2 text-[11.5px] leading-relaxed text-forest-700">
          Request created and pending a different operator.{" "}
          <Link href={`/platform/approvals/${created.id}`} className="underline">
            Open the request
          </Link>{" "}
          to review or execute it once approved. Nothing has changed on the tenant yet.
        </p>
      ) : null}
    </div>
  );
}
