"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/ui/modal";
import { postJson } from "@/lib/client-api";
import {
  approvalActionLabel,
  approvalStatusLabel,
} from "@/lib/platform";
import type { PlatformApproval } from "@/lib/platform-types";

type Mode = "approve" | "reject" | "execute" | "cancel" | null;

const COPY: Record<Exclude<Mode, null>, { title: string; description: string; button: string }> = {
  approve: {
    title: "Approve this request?",
    description:
      "Approval does not change the tenant. It makes this exact target, action and reason executable once by an operator with the execution capability.",
    button: "Confirm approval",
  },
  reject: {
    title: "Reject this request?",
    description:
      "Rejection is terminal. This request cannot be approved, revived or executed; a new request would be needed.",
    button: "Confirm rejection",
  },
  execute: {
    title: "Execute the approved change?",
    description:
      "This applies the tenant lifecycle change now. Execution is atomic and can happen only once; the approval is marked executed in the same transaction.",
    button: "Execute change",
  },
  cancel: {
    title: "Cancel your request?",
    description:
      "Cancellation is terminal. The target tenant is not changed, and this request cannot be revived.",
    button: "Confirm cancellation",
  },
};

export function ApprovalReview({ approval }: { approval: PlatformApproval }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const closed = mode === null;
  const copy = mode ? COPY[mode] : null;

  async function submit() {
    if (!mode || pending) return;
    setPending(true);
    setError(null);
    const path = `/platform/approvals/${approval.id}/${mode}`;
    const body =
      mode === "approve" || mode === "reject" ? { reason: note.trim() || null } : {};
    const result = await postJson<PlatformApproval>(path, body);
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMessage(
      mode === "execute"
        ? "The approved change was executed. The tenant state and audit journal are updated."
        : mode === "approve"
          ? "Request approved. It can now be executed exactly once by an authorised operator."
          : mode === "reject"
            ? "Request rejected. It is terminal and cannot be revived."
            : "Request cancelled. Nothing on the tenant was changed.",
    );
    setMode(null);
    setNote("");
    router.refresh();
  }

  const actionable = approval.can_decide || approval.can_execute || approval.can_cancel;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {approval.can_decide ? (
          <>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setMode("approve");
              }}
              className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 hover:bg-forest-800"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setMode("reject");
              }}
              className="h-9 rounded-lg border border-rust-500/30 bg-rust-500/10 px-3.5 text-[12px] font-medium text-rust-500 hover:bg-rust-500/15"
            >
              Reject
            </button>
          </>
        ) : null}

        {approval.can_execute ? (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setMode("execute");
            }}
            className="h-9 rounded-lg bg-rust-500 px-3.5 text-[12px] font-medium text-paper-50 hover:bg-rust-500/90"
          >
            Execute {approvalActionLabel(approval.action).toLowerCase()}
          </button>
        ) : null}

        {approval.can_cancel ? (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setMode("cancel");
            }}
            className="h-9 rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100"
          >
            Cancel request
          </button>
        ) : null}

        {!actionable ? (
          <p className="text-[11.5px] leading-relaxed text-ink-500">
            No action is available to you on this request. It may be awaiting a different
            operator, may have reached a terminal state, or your role may lack the capability.
          </p>
        ) : null}
      </div>

      <p className="text-[10.5px] leading-relaxed text-ink-400">
        Current state: <span className="font-medium text-ink-600">{approvalStatusLabel(approval.status)}</span>.
        The API re-checks the state, the requester, the capability and the exact target on every
        action; a stale screen cannot force a transition.
      </p>

      {error ? (
        <p role="alert" className="text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="text-[11.5px] leading-relaxed text-forest-700">
          {message}
        </p>
      ) : null}

      <Modal
        open={!closed}
        onClose={() => {
          if (pending) return;
          setMode(null);
          setError(null);
        }}
        title={copy?.title ?? ""}
        description={copy?.description}
        width="max-w-xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setMode(null)}
              disabled={pending}
              className="h-9 rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100 disabled:opacity-50"
            >
              Keep request unchanged
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={pending}
              className={[
                "h-9 rounded-lg px-3.5 text-[12px] font-medium text-paper-50 disabled:opacity-50",
                mode === "approve" ? "bg-forest-900 hover:bg-forest-800" : "bg-rust-500 hover:bg-rust-500/90",
              ].join(" ")}
            >
              {pending ? "Applying…" : copy?.button}
            </button>
          </>
        }
      >
        <dl className="mb-3 space-y-1.5 rounded-lg border border-paper-200 bg-paper-50 p-3 text-[11.5px]">
          <div className="flex justify-between gap-3">
            <dt className="text-ink-400">Organisation</dt>
            <dd className="text-right font-medium text-ink-800">
              {approval.organization_name ?? approval.organization_id}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-400">Action</dt>
            <dd className="text-ink-800">{approvalActionLabel(approval.action)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-400">Requested by</dt>
            <dd className="truncate text-ink-800">{approval.requested_by ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-ink-400">Reason</dt>
            <dd className="max-w-[70%] text-right text-ink-700">{approval.reason ?? "—"}</dd>
          </div>
        </dl>

        {mode === "approve" || mode === "reject" ? (
          <label className="block">
            <span className="label-mono text-[8.5px] text-ink-400">
              Decision note (optional, recorded in the audit journal)
            </span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={400}
              className="mt-1 w-full rounded-lg border border-paper-300 bg-paper-50 p-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
            />
          </label>
        ) : null}
        {mode === "execute" ? (
          <p className="text-[11.5px] leading-relaxed text-ink-600">
            The request was approved by <strong>{approval.decided_by ?? "another operator"}</strong>.
            Executing suspends or reactivates the tenant immediately. Existing memberships and records
            are preserved.
          </p>
        ) : null}
      </Modal>
    </div>
  );
}
