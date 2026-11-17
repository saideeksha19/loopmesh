"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { getJson, postJson } from "@/lib/client-api";
import { formatQuantity } from "@/lib/format";

type Kind = "proposal" | "transaction";

type FieldSpec = {
  name: string;
  label: string;
  type?: "text" | "number" | "textarea" | "date" | "select";
  required?: boolean;
  placeholder?: string;
  hint?: string;
  options?: { value: string; label: string }[];
};

type ActionSpec = {
  label: string;
  confirm: string;
  irreversible?: boolean;
  fields: FieldSpec[];
};

const REASON_FIELD: FieldSpec = {
  name: "reason",
  label: "Reason",
  type: "textarea",
  required: true,
  placeholder: "Why is this happening? Recorded permanently in the audit journal.",
};

const ACTION_SPECS: Record<string, ActionSpec> = {
  submit: {
    label: "Submit for review",
    confirm: "Submit this draft? The receiving organisation can then review it.",
    fields: [
      {
        name: "reason",
        label: "Note to the reviewer",
        type: "textarea",
        placeholder: "Optional context for the receiving organisation",
      },
    ],
  },
  review: {
    label: "Start review",
    confirm: "Move this proposal into formal review?",
    fields: [
      { name: "reason", label: "Review note", type: "textarea", placeholder: "Optional" },
    ],
  },
  approve: {
    label: "Approve",
    confirm:
      "Approving authorises physical execution. An evidence reference is mandatory and the decision is permanent.",
    irreversible: true,
    fields: [
      {
        name: "approval_reference",
        label: "Decision evidence reference",
        required: true,
        placeholder: "e.g. DEMO-APPR-2026-0042",
        hint: "Recorded with the approval. Never invent a real decision reference.",
      },
      { name: "reason", label: "Decision note", type: "textarea", placeholder: "Optional" },
    ],
  },
  reject: {
    label: "Reject",
    confirm: "Rejection is terminal. The proposal cannot be reopened.",
    irreversible: true,
    fields: [REASON_FIELD],
  },
  withdraw: {
    label: "Withdraw",
    confirm: "Withdrawing closes this proposal. It cannot be resubmitted.",
    irreversible: true,
    fields: [
      { name: "reason", label: "Reason", type: "textarea", placeholder: "Optional" },
    ],
  },
  record_transfer: {
    label: "Record transfer",
    confirm:
      "Record the quantity that physically moved. Verification must be performed by a different actor.",
    fields: [
      {
        name: "transferred_quantity",
        label: "Transferred quantity",
        type: "number",
        required: true,
      },
      {
        name: "transfer_reference",
        label: "Weighbridge / delivery reference",
        required: true,
        placeholder: "e.g. DEMO-WB-2026-0042",
      },
      {
        name: "material_identification",
        label: "Material identification",
        required: true,
        placeholder: "Batch, lot or consignment identifier",
      },
      { name: "transferred_at", label: "Transfer date", type: "date" },
      { name: "carrier_name", label: "Carrier", type: "text", placeholder: "Optional" },
      { name: "notes", label: "Notes", type: "textarea", placeholder: "Optional" },
    ],
  },
  verify: {
    label: "Verify quantity",
    confirm:
      "Verification makes this material count as recovered impact. It requires evidence and cannot be undone.",
    irreversible: true,
    fields: [
      {
        name: "verified_quantity",
        label: "Verified quantity",
        type: "number",
        required: true,
      },
      {
        name: "verification_method",
        label: "Method",
        type: "select",
        required: true,
        options: [
          { value: "weighbridge_ticket", label: "Weighbridge ticket" },
          { value: "third_party_audit", label: "Third-party audit" },
          { value: "laboratory_assay", label: "Laboratory assay" },
          { value: "supplier_declaration", label: "Supplier declaration" },
          { value: "other", label: "Other" },
        ],
      },
      {
        name: "evidence_reference",
        label: "Evidence reference",
        required: true,
        placeholder: "Ticket, assay or audit reference",
      },
      { name: "notes", label: "Notes", type: "textarea", placeholder: "Optional" },
    ],
  },
  cancel: {
    label: "Cancel",
    confirm: "Cancelling closes this transaction and its proposal. This is terminal.",
    irreversible: true,
    fields: [REASON_FIELD],
  },
};

// Action identifiers are snake_case; the REST paths are kebab-case.
const ACTION_PATHS: Record<string, string> = {
  record_transfer: "record-transfer",
};

function missingRequired(action: string, values: Record<string, string>): string | null {
  const spec = ACTION_SPECS[action];
  for (const field of spec.fields) {
    if (field.required && !`${values[field.name] ?? ""}`.trim()) {
      return `${field.label} is required.`;
    }
  }
  const reason = values.reason?.trim();
  if ((action === "reject" || action === "cancel") && (!reason || reason.length < 5)) {
    return "A reason of at least 5 characters is required for this transition.";
  }
  return null;
}

function buildBody(action: string, values: Record<string, string>): Record<string, unknown> {
  const reason = values.reason?.trim();
  const notes = values.notes?.trim();

  switch (action) {
    case "approve":
      return {
        approval_reference: values.approval_reference?.trim(),
        reason: reason || undefined,
        evidence: { note: reason || "Approval recorded in the LOOPMESH workspace." },
      };
    case "record_transfer":
      return {
        transferred_quantity: Number(values.transferred_quantity),
        transfer_reference: values.transfer_reference?.trim(),
        material_identification: values.material_identification?.trim(),
        transferred_at: values.transferred_at
          ? new Date(`${values.transferred_at}T12:00:00Z`).toISOString()
          : undefined,
        carrier_name: values.carrier_name?.trim() || undefined,
        notes: notes || undefined,
      };
    case "verify":
      return {
        verified_quantity: Number(values.verified_quantity),
        verification_method: values.verification_method,
        evidence_reference: values.evidence_reference?.trim(),
        evidence: notes ? { note: notes } : undefined,
        notes: notes || undefined,
      };
    default:
      return { reason: reason || undefined };
  }
}

export function ActionBar({
  kind,
  endpoint,
  initialActions,
  version,
  acceptedQuantity,
  unit,
}: {
  kind: Kind;
  endpoint: string;
  initialActions: string[];
  version: number;
  acceptedQuantity?: number | null;
  unit: string;
}) {
  const router = useRouter();
  const [actions, setActions] = useState<string[]>(initialActions);
  const [openAction, setOpenAction] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);

  // Permissions depend on the selected actor and on the record's state, so the
  // available actions are re-read whenever either can have changed.
  const loadActions = useCallback(async () => {
    const result = await getJson<{ available_actions: string[] }>(endpoint);
    if (result.ok) setActions(result.data.available_actions);
  }, [endpoint]);

  useEffect(() => {
    void loadActions();
  }, [loadActions]);

  const spec = openAction ? ACTION_SPECS[openAction] : null;

  function start(action: string) {
    setOpenAction(action);
    setError(null);
    setSuccess(null);
    setValues(
      action === "record_transfer"
        ? {
            transferred_quantity: acceptedQuantity ? String(acceptedQuantity) : "",
          }
        : action === "verify"
          ? {
              verified_quantity: acceptedQuantity ? String(acceptedQuantity) : "",
              verification_method: "weighbridge_ticket",
            }
          : {},
    );
  }

  async function submit() {
    if (!openAction) return;
    const invalid = missingRequired(openAction, values);
    if (invalid) {
      setError(invalid);
      return;
    }
    setPending(true);
    setError(null);
    const body = { ...buildBody(openAction, values), expected_version: version };
    const path = ACTION_PATHS[openAction] ?? openAction;
    const result = await postJson<unknown>(`${endpoint}/${path}`, body);
    setPending(false);
    if (!result.ok) {
      setError(result.fields?.length ? `${result.error} — ${result.fields.join("; ")}` : result.error);
      return;
    }
    setSuccess(`${ACTION_SPECS[openAction].label} recorded.`);
    setOpenAction(null);
    await loadActions();
    router.refresh();
  }

  const sorted = useMemo(() => {
    const order =
      kind === "proposal"
        ? ["submit", "review", "approve", "reject", "withdraw"]
        : ["record_transfer", "verify", "reject", "cancel"];
    return [...actions].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  }, [actions, kind]);

  return (
    <div className="px-4 py-4 sm:px-5">
      {success ? (
        <p className="mb-3 rounded-lg border border-lime-500/40 bg-lime-400/15 px-3 py-2 text-[11.5px] text-forest-800">
          {success}
        </p>
      ) : null}

      {sorted.length === 0 ? (
        <p className="text-[11.5px] leading-relaxed text-ink-400">
          No actions are available to this actor in this state. Switch identity to a role with the
          required authority, or check the transition rules.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {sorted.map((action) => {
            const actionSpec = ACTION_SPECS[action];
            if (!actionSpec) return null;
            const destructive = action === "reject" || action === "cancel";
            return (
              <button
                key={action}
                type="button"
                onClick={() => start(action)}
                className={[
                  "rounded-lg border px-3 py-1.5 text-[11.5px] font-medium transition-colors",
                  destructive
                    ? "border-rust-500/35 bg-rust-500/10 text-rust-500 hover:bg-rust-500/15"
                    : "border-forest-700/25 bg-forest-800/[0.07] text-forest-700 hover:bg-forest-800/[0.12]",
                ].join(" ")}
              >
                {actionSpec.label}
              </button>
            );
          })}
        </div>
      )}

      <Modal
        open={openAction !== null}
        onClose={() => setOpenAction(null)}
        title={spec ? spec.label : "Confirm"}
        description={spec?.confirm}
        width="max-w-xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setOpenAction(null)}
              className="rounded-lg border border-paper-300 px-3 py-1.5 text-[11.5px] text-ink-600 hover:bg-paper-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={pending}
              className="rounded-lg bg-forest-800 px-3 py-1.5 text-[11.5px] font-medium text-paper-50 disabled:opacity-60"
            >
              {pending ? "Recording…" : spec?.label ?? "Confirm"}
            </button>
          </>
        }
      >
        {openAction ? (
          <div className="space-y-3">
            {kind === "transaction" && openAction !== "verify" ? (
              <p className="text-[11px] text-ink-400">
                Contracted quantity{" "}
                {acceptedQuantity ? formatQuantity(acceptedQuantity, unit) : "—"}.
              </p>
            ) : null}

            {spec?.irreversible ? (
              <p className="rounded-lg border border-clay-500/30 bg-clay-500/10 px-3 py-2 text-[11px] leading-relaxed text-clay-500">
                This transition is recorded permanently. It cannot be reversed through the API.
              </p>
            ) : null}

            {(spec?.fields ?? []).map((field) => (
              <label key={field.name} className="block">
                <span className="label-mono text-[8.5px] text-ink-400">
                  {field.label}
                  {field.required ? " *" : ""}
                </span>
                {field.type === "textarea" ? (
                  <textarea
                    rows={3}
                    value={values[field.name] ?? ""}
                    onChange={(event) =>
                      setValues((previous) => ({ ...previous, [field.name]: event.target.value }))
                    }
                    placeholder={field.placeholder}
                    className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
                  />
                ) : field.type === "select" ? (
                  <select
                    value={values[field.name] ?? field.options?.[0]?.value}
                    onChange={(event) =>
                      setValues((previous) => ({ ...previous, [field.name]: event.target.value }))
                    }
                    className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
                  >
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={field.type ?? "text"}
                    step={field.type === "number" ? "0.001" : undefined}
                    value={values[field.name] ?? ""}
                    onChange={(event) =>
                      setValues((previous) => ({ ...previous, [field.name]: event.target.value }))
                    }
                    placeholder={field.placeholder}
                    className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
                  />
                )}
                {field.hint ? (
                  <span className="mt-1 block text-[10px] text-ink-300">{field.hint}</span>
                ) : null}
              </label>
            ))}

            {error ? (
              <p className="rounded-lg border border-rust-500/30 bg-rust-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rust-500">
                {error}
              </p>
            ) : null}

            <div className="flex items-center gap-2 pt-1">
              <Badge tone="outline" mono>
                optimistic version {version}
              </Badge>
              <span className="text-[10px] text-ink-300">
                Server-side authorization decides; this dialog does not grant it.
              </span>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
