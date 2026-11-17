"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { postJson } from "@/lib/client-api";
import {
  SUSPENSION_EFFECTS,
  platformStatusLabel,
  platformStatusTone,
} from "@/lib/platform";
import type {
  PlatformApproval,
  PlatformOrganizationDetail,
} from "@/lib/platform-types";

type Mode = "suspend" | "reactivate" | null;

const MIN_REASON = 8;

/**
 * Creates a two-person approval request; it never changes the tenant directly.
 * The API requires the operator flag, the request and lifecycle capabilities, a
 * written reason for suspension and a valid source state. A different operator
 * must approve, and execution is a separate action on the request.
 */
export function OrganizationStatus({
  organization,
  canManage,
}: {
  organization: Pick<PlatformOrganizationDetail, "id" | "name" | "slug" | "status">;
  canManage: boolean;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const suspended = organization.status === "suspended";
  const reasonTooShort = mode === "suspend" && reason.trim().length < MIN_REASON;

  async function submit() {
    if (!mode || reasonTooShort || pending) return;
    setPending(true);
    setError(null);
    const result = await postJson<PlatformApproval>("/platform/approvals", {
      organization_id: organization.id,
      action: mode === "suspend" ? "suspend" : "reactivate",
      reason: reason.trim() || null,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setMessage(
      mode === "suspend"
        ? `Suspension requested for ${organization.name}. The tenant is unchanged until a different operator approves the request and it is executed.`
        : `Reactivation requested for ${organization.name}. The tenant is unchanged until a different operator approves the request and it is executed.`,
    );
    setMode(null);
    setReason("");
    router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={platformStatusTone(organization.status)} mono>
        {platformStatusLabel(organization.status)}
      </Badge>

      {canManage ? (
        <button
          type="button"
          onClick={() => {
            setError(null);
            setMode(suspended ? "reactivate" : "suspend");
          }}
          className={[
            "h-8 rounded-lg px-3 text-[11.5px] font-medium transition-colors",
            suspended
              ? "bg-forest-900 text-lime-300 hover:bg-forest-800"
              : "border border-rust-500/30 bg-rust-500/10 text-rust-500 hover:bg-rust-500/15",
          ].join(" ")}
        >
          {suspended ? "Request reactivation" : "Request suspension"}
        </button>
      ) : (
        <span className="text-[10.5px] text-ink-400">
          Your platform role can inspect this tenant but not change its lifecycle.
        </span>
      )}

      {message ? (
        <p role="status" className="basis-full text-[11.5px] text-forest-700">
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="basis-full text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}

      <Modal
        open={mode !== null}
        onClose={() => {
          if (pending) return;
          setMode(null);
          setError(null);
        }}
        title={
          mode === "reactivate"
            ? `Request reactivation of ${organization.name}?`
            : `Request suspension of ${organization.name}?`
        }
        description={
          mode === "reactivate"
            ? "This creates a request. A different operator must approve it before anyone can execute the change; the tenant stays suspended until then."
            : "This creates a request. A different operator must approve it before anyone can execute the change; the tenant keeps operating until then."
        }
        width="max-w-xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => {
                setMode(null);
                setError(null);
              }}
              disabled={pending}
              className="h-9 rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={pending || reasonTooShort}
              className={[
                "h-9 rounded-lg px-3.5 text-[12px] font-medium text-paper-50 transition-colors disabled:opacity-50",
                mode === "reactivate"
                  ? "bg-forest-900 hover:bg-forest-800"
                  : "bg-rust-500 hover:bg-rust-500/90",
              ].join(" ")}
            >
              {pending
                ? "Requesting…"
                : mode === "reactivate"
                  ? "Create reactivation request"
                  : "Create suspension request"}
            </button>
          </>
        }
      >
        {mode === "suspend" ? (
          <div className="space-y-3">
            <ul className="space-y-1.5">
              {SUSPENSION_EFFECTS.map((effect) => (
                <li key={effect} className="flex items-start gap-2 text-[12px] leading-relaxed text-ink-600">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-clay-500" />
                  <span>{effect}</span>
                </li>
              ))}
            </ul>
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">
                Suspension reason (recorded in the audit journal, at least {MIN_REASON} characters)
              </span>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                maxLength={400}
                className="mt-1 w-full rounded-lg border border-paper-300 bg-paper-50 p-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
              />
            </label>
            <p className="font-mono text-[9.5px] text-ink-400">{reason.trim().length}/400</p>
          </div>
        ) : (
          <p className="text-[12px] leading-relaxed text-ink-600">
            Every membership, invitation and audit record is preserved while the tenant is
            suspended. Reactivation restores access for the members already on the roster; it does
            not recreate anything that was removed. Creating this request does not change the
            tenant.
          </p>
        )}

      </Modal>
    </div>
  );
}
