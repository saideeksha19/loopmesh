import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { ActionBar } from "@/components/workflow/action-bar";
import { ActorSwitcher } from "@/components/workflow/actor-switcher";
import { AuditTimeline } from "@/components/workflow/audit-timeline";
import { TransitionTimeline } from "@/components/workflow/history-timeline";
import { TransactionStatusBadge } from "@/components/workflow/status-badge";
import { apiGet } from "@/lib/api";
import { formatDate, formatNumber, formatQuantity, titleCase } from "@/lib/format";
import type { AuditRecord, TransactionDetail } from "@/lib/workflow-types";

export const dynamic = "force-dynamic";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-paper-200 py-2 last:border-0">
      <p className="label-mono text-[8px] text-ink-400">{label}</p>
      <p className="mt-0.5 text-[11.5px] text-ink-700">{value}</p>
    </div>
  );
}

export default async function TransactionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [transaction, audit] = await Promise.all([
    apiGet<TransactionDetail>(`/transactions/${id}`),
    apiGet<AuditRecord[]>(`/audit/transaction/${id}`),
  ]);

  if (!transaction.ok) {
    return (
      <>
        <PageHeader eyebrow="Transaction" title="Transaction unavailable" description={transaction.error} />
        <DataUnavailable message={transaction.error} title="Transaction unavailable" />
      </>
    );
  }

  const record = transaction.data;
  const evidence = Object.entries(record.evidence ?? {});

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2 font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">
        <Link href="/transactions" className="hover:underline">
          ← transactions
        </Link>
        <span>/</span>
        <Link href={`/proposals/${record.proposal_id}`} className="hover:underline">
          proposal {record.proposal_id.slice(0, 8)}
        </Link>
        {record.is_demo ? <Badge tone="muted">demo record</Badge> : null}
      </div>

      <PageHeader
        eyebrow="Recovery transaction · evidence interface"
        title={record.material_name ?? "Recovery transaction"}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <TransactionStatusBadge status={record.status} />
            <span className="text-[12px]">
              {record.source_organization_name ?? "—"} →{" "}
              {record.destination_organization_name ?? "—"} ·{" "}
              {formatQuantity(record.transferred_quantity ?? record.accepted_quantity ?? 0, record.unit)}
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
              title="Execution controls"
              subtitle="Recording a transfer and verifying it are separate authority steps. The verifier must differ from the recorder."
            />
            <ActionBar
              kind="transaction"
              endpoint={`/transactions/${record.id}`}
              initialActions={record.available_actions}
              version={record.version}
              acceptedQuantity={record.transferred_quantity ?? record.accepted_quantity}
              unit={record.unit}
            />
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="Mass balance"
              title="Quantities"
              subtitle="Verified mass can never exceed the transferred mass, and neither is derived from the proposed quantity."
            />
            <div className="grid gap-x-6 px-5 py-3 sm:grid-cols-3">
              <div>
                <p className="label-mono text-[8px] text-ink-400">Contracted</p>
                <p className="figure mt-1 text-[16px] text-ink-800">
                  {record.accepted_quantity !== null
                    ? formatQuantity(record.accepted_quantity, record.unit)
                    : "—"}
                </p>
              </div>
              <div>
                <p className="label-mono text-[8px] text-ink-400">Transferred</p>
                <p className="figure mt-1 text-[16px] text-ink-800">
                  {record.transferred_quantity !== null
                    ? formatQuantity(record.transferred_quantity, record.unit)
                    : "—"}
                </p>
              </div>
              <div>
                <p className="label-mono text-[8px] text-ink-400">Verified · counts as impact</p>
                <p className="figure mt-1 text-[16px] text-forest-800">
                  {record.verified_quantity !== null
                    ? formatQuantity(record.verified_quantity, record.unit)
                    : "not counted"}
                </p>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="Evidence"
              title="Transfer and verification record"
              subtitle="Evidence references are stored verbatim. No document is inferred or fabricated."
            />
            <div className="grid gap-x-6 px-5 py-3 sm:grid-cols-2">
              <Field label="Material identification" value={record.material_identification ?? "—"} />
              <Field label="Transfer reference" value={record.transfer_reference ?? "—"} />
              <Field label="Carrier" value={record.carrier_name ?? "—"} />
              <Field
                label="Distance"
                value={
                  record.transport_distance_km !== null
                    ? `${formatNumber(record.transport_distance_km, 1)} km`
                    : "—"
                }
              />
              <Field label="Transferred at" value={formatDate(record.transferred_at)} />
              <Field label="Recorded by" value={record.transfer_recorded_by ?? "—"} />
              <Field
                label="Verification method"
                value={record.verification_method ? titleCase(record.verification_method) : "—"}
              />
              <Field label="Verified by" value={record.verified_by ?? "—"} />
              <Field label="Verified at" value={formatDate(record.verified_at)} />
              <Field label="Rejection reason" value={record.rejection_reason ?? "—"} />
              <Field label="Cancellation reason" value={record.cancellation_reason ?? "—"} />
              <Field label="Notes" value={record.notes ?? "—"} />
            </div>
            {evidence.length ? (
              <div className="border-t border-paper-200 px-5 py-3">
                <p className="label-mono text-[8px] text-ink-400">Evidence payload</p>
                <dl className="mt-1.5 grid gap-1">
                  {evidence.map(([key, value]) => (
                    <div key={key} className="flex gap-2 text-[11px]">
                      <dt className="min-w-[150px] font-mono text-[9px] tracking-wide text-ink-300 uppercase">
                        {key}
                      </dt>
                      <dd className="break-words text-ink-600">
                        {typeof value === "object" ? JSON.stringify(value) : String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader eyebrow="History" title="Transition history" />
            <TransitionTimeline items={record.history} />
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader
              eyebrow="Audit journal"
              title="Event timeline"
              subtitle="Includes denied authorization attempts against this transaction."
            />
            <AuditTimeline
              events={audit.ok ? audit.data : []}
              emptyTitle="No audit events recorded yet"
              emptyDescription="Recording a transfer or attempting an unauthorized action writes an audit record."
            />
          </Panel>

          <Panel>
            <PanelHeader eyebrow="Accounting" title="What this means" />
            <p className="px-5 py-4 text-[11.5px] leading-relaxed text-ink-500">
              A transaction becomes recovered material only when it is verified with evidence. Moving
              between states cannot increase the recovered total: the ledger counts verified
              quantities once and never re-counts them as pipeline.
            </p>
          </Panel>
        </div>
      </div>
    </>
  );
}
