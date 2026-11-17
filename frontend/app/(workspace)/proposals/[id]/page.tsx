import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { ActionBar } from "@/components/workflow/action-bar";
import { ActorSwitcher } from "@/components/workflow/actor-switcher";
import { AuditTimeline } from "@/components/workflow/audit-timeline";
import { CreateTransactionButton } from "@/components/workflow/create-transaction-button";
import { TransitionTimeline } from "@/components/workflow/history-timeline";
import { ProposalStatusBadge, TransactionStatusBadge } from "@/components/workflow/status-badge";
import { apiGet } from "@/lib/api";
import { hasPermission } from "@/lib/auth";
import { formatDate, formatQuantity, titleCase } from "@/lib/format";
import { loadSession } from "@/lib/session";
import type { AuditRecord, ProposalDetail } from "@/lib/workflow-types";

export const dynamic = "force-dynamic";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-paper-200 py-2 last:border-0">
      <p className="label-mono text-[8px] text-ink-400">{label}</p>
      <p className="mt-0.5 text-[11.5px] text-ink-700">{value}</p>
    </div>
  );
}

export default async function ProposalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [proposal, audit, session] = await Promise.all([
    apiGet<ProposalDetail>(`/proposals/${id}`),
    apiGet<AuditRecord[]>(`/audit/proposal/${id}`),
    loadSession(),
  ]);

  if (!proposal.ok) {
    return (
      <>
        <PageHeader eyebrow="Proposal" title="Proposal unavailable" description={proposal.error} />
        <DataUnavailable message={proposal.error} title="Proposal unavailable" />
      </>
    );
  }

  const record = proposal.data;
  const transaction = record.transaction;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2 font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">
        <Link href="/proposals" className="hover:underline">
          ← proposals
        </Link>
        <span>/</span>
        <span>{record.id.slice(0, 8)}</span>
        {record.is_demo ? <Badge tone="muted">demo record</Badge> : null}
      </div>

      <PageHeader
        eyebrow="Recovery proposal · lifecycle"
        title={record.material_name ?? "Recovery proposal"}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ProposalStatusBadge status={record.status} />
            <span className="text-[12px]">
              {record.supplier_name ?? "—"} → {record.consumer_name ?? "—"} ·{" "}
              {formatQuantity(record.quantity, record.unit)}
            </span>
          </span>
        }
        actions={<ActorSwitcher />}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Panel>
            <PanelHeader
              eyebrow="Available transitions"
              title="Lifecycle controls"
              subtitle="Only transitions valid for the current state are accepted. Every action is authorised server-side and recorded with actor, timestamp and reason."
            />
            <ActionBar
              kind="proposal"
              endpoint={`/proposals/${record.id}`}
              initialActions={record.available_actions}
              version={record.version}
              acceptedQuantity={record.quantity}
              unit={record.unit}
            />
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="Evidence trail"
              title="Decision record"
              subtitle="Approval evidence, reasons and timestamps are written once and never edited."
            />
            <div className="grid gap-x-6 px-5 py-3 sm:grid-cols-2">
              <Field label="Submitted" value={`${record.submitted_by ?? "—"} · ${formatDate(record.submitted_at)}`} />
              <Field label="Reviewed" value={`${record.reviewed_by ?? "—"} · ${formatDate(record.reviewed_at)}`} />
              <Field label="Approved by" value={record.approved_by ?? "—"} />
              <Field label="Approved at" value={formatDate(record.approved_at)} />
              <Field label="Approval reference" value={record.approval_reference ?? "—"} />
              <Field label="Compatibility" value={titleCase(record.compatibility_status)} />
              <Field label="Rejection reason" value={record.rejection_reason ?? "—"} />
              <Field label="Cancellation reason" value={record.cancellation_reason ?? "—"} />
              <Field label="Failure reason" value={record.failure_reason ?? "—"} />
              <Field label="Valid until" value={formatDate(record.valid_until)} />
            </div>
            {Object.keys(record.approval_evidence).length ? (
              <div className="border-t border-paper-200 px-5 py-3">
                <p className="label-mono text-[8px] text-ink-400">Approval evidence payload</p>
                <dl className="mt-1.5 grid gap-1">
                  {Object.entries(record.approval_evidence).map(([key, value]) => (
                    <div key={key} className="flex gap-2 text-[11px]">
                      <dt className="font-mono text-[9px] tracking-wide text-ink-300 uppercase">
                        {key}
                      </dt>
                      <dd className="text-ink-600">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}
            {record.notes ? (
              <p className="border-t border-paper-200 px-5 py-3 text-[11.5px] leading-relaxed text-ink-500">
                {record.notes}
              </p>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="History"
              title="Transition history"
              subtitle="Append-only. Rows are never updated or deleted by the API."
            />
            <TransitionTimeline
              items={record.history}
              emptyNote="This proposal predates the lifecycle or has not been actioned yet."
            />
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader
              eyebrow="Execution"
              title="Recovery transaction"
              subtitle="A transaction can only be created from an approved proposal. Verification is a separate role."
            />
            {transaction ? (
              <div className="space-y-3 px-5 py-4">
                <div className="flex items-center gap-2">
                  <TransactionStatusBadge status={transaction.status} />
                  <Link
                    href={`/transactions/${transaction.id}`}
                    className="font-mono text-[9.5px] tracking-wide text-forest-700 uppercase hover:underline"
                  >
                    open transaction
                  </Link>
                </div>
                <div className="grid gap-2">
                  <Field
                    label="Contracted"
                    value={formatQuantity(transaction.accepted_quantity ?? 0, transaction.unit)}
                  />
                  <Field
                    label="Transferred"
                    value={
                      transaction.transferred_quantity !== null
                        ? formatQuantity(transaction.transferred_quantity, transaction.unit)
                        : "—"
                    }
                  />
                  <Field
                    label="Verified"
                    value={
                      transaction.verified_quantity !== null
                        ? formatQuantity(transaction.verified_quantity, transaction.unit)
                        : "not counted as recovered"
                    }
                  />
                  <Field
                    label="Transfer reference"
                    value={transaction.transfer_reference ?? "—"}
                  />
                  <Field label="Verification method" value={transaction.verification_method ? titleCase(transaction.verification_method) : "—"} />
                </div>
              </div>
            ) : (
              <div className="space-y-3 px-5 py-4">
                <p className="text-[11.5px] leading-relaxed text-ink-500">
                  {record.status === "approved"
                    ? "This proposal is approved. Create the transaction to start execution."
                    : "No transaction yet. The proposal must be approved before execution can start."}
                </p>
                {record.status === "approved" ? (
                  <CreateTransactionButton
                    proposalId={record.id}
                    canCreate={hasPermission(
                      session.status === "authenticated" ? session.user : null,
                      "transaction.create",
                    )}
                  />
                ) : null}
              </div>
            )}
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="Audit journal"
              title="Event timeline"
              subtitle="Server-written events for this record, including denied attempts."
            />
            <AuditTimeline
              events={audit.ok ? audit.data : []}
              emptyTitle="No audit events recorded yet"
              emptyDescription="Creating, submitting or reviewing this proposal writes an immutable audit record."
            />
          </Panel>
        </div>
      </div>
    </>
  );
}
