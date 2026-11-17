"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { ProposalStatusBadge } from "@/components/workflow/status-badge";
import { postJson } from "@/lib/client-api";
import { formatDate, formatQuantity, relativeTime } from "@/lib/format";
import type { Opportunity } from "@/lib/types";
import type { ProposalDetail, ProposalSummary } from "@/lib/workflow-types";

const FILTERS = [
  { key: "all", label: "All", states: [] as string[] },
  { key: "pipeline", label: "In pipeline", states: ["draft", "submitted", "under_review"] },
  { key: "approved", label: "Approved", states: ["approved"] },
  { key: "executing", label: "Executing", states: ["in_progress"] },
  { key: "completed", label: "Completed", states: ["completed"] },
  {
    key: "closed",
    label: "Closed",
    states: ["rejected", "withdrawn", "cancelled", "failed"],
  },
];

export function ProposalWorkspace({
  proposals,
  opportunities,
  canCreate,
}: {
  proposals: ProposalSummary[];
  opportunities: Opportunity[];
  canCreate: boolean;
}) {
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    opportunity_id: "",
    quantity: "",
    price: "",
    notes: "",
  });

  const available = useMemo(
    () =>
      opportunities.filter(
        (opportunity) =>
          opportunity.compatibility_status !== "incompatible" &&
          opportunity.status !== "converted",
      ),
    [opportunities],
  );

  const selected = available.find((item) => item.id === form.opportunity_id);

  const visible = useMemo(() => {
    const active = FILTERS.find((item) => item.key === filter) ?? FILTERS[0];
    const needle = query.trim().toLowerCase();
    return proposals.filter((proposal) => {
      if (active.states.length && !active.states.includes(proposal.status)) return false;
      if (!needle) return true;
      return [
        proposal.material_name,
        proposal.material_reference,
        proposal.supplier_name,
        proposal.consumer_name,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [proposals, filter, query]);

  const pageSize = 15;
  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const paged = visible.slice(currentPage * pageSize, currentPage * pageSize + pageSize);

  async function create() {
    setPending(true);
    setError(null);
    const result = await postJson<ProposalDetail>("/proposals", {
      opportunity_id: form.opportunity_id,
      quantity: Number(form.quantity),
      price_per_unit: form.price ? Number(form.price) : null,
      notes: form.notes || null,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.fields?.length ? `${result.error} — ${result.fields.join("; ")}` : result.error);
      return;
    }
    setCreating(false);
    router.push(`/proposals/${result.data.id}`);
    router.refresh();
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => {
          const count = item.states.length
            ? proposals.filter((proposal) => item.states.includes(proposal.status)).length
            : proposals.length;
          const active = filter === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setFilter(item.key);
                setPage(0);
              }}
              className={[
                "rounded-lg border px-2.5 py-1.5 font-mono text-[10px] tracking-wide uppercase transition-colors",
                active
                  ? "border-forest-700/30 bg-forest-800/[0.09] text-forest-700"
                  : "border-paper-300 bg-paper-50 text-ink-500 hover:bg-paper-100",
              ].join(" ")}
            >
              {item.label} · {count}
            </button>
          );
        })}
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(0);
          }}
          placeholder="Search material, reference or organisation"
          className="ml-auto w-full max-w-[280px] rounded-lg border border-paper-300 bg-[#fffdf8] px-3 py-1.5 text-[11.5px] text-ink-800"
          aria-label="Search proposals"
        />
      </div>

      <div className="panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-paper-200 px-5 py-4">
          <div>
            <p className="label-mono text-[8.5px] text-ink-400">Proposal workspace</p>
            <h2 className="text-[15px] font-semibold text-ink-900">
              {visible.length} of {proposals.length} proposals
            </h2>
          </div>
          {canCreate ? (
            <button
              type="button"
              onClick={() => {
                setCreating(true);
                setError(null);
              }}
              className="rounded-lg bg-forest-800 px-3 py-1.5 text-[11.5px] font-medium text-paper-50"
            >
              New draft proposal
            </button>
          ) : null}
        </div>

        {visible.length === 0 ? (
          <EmptyState
            title="No proposals in this view"
            description="Create a draft from a screened opportunity, then submit it for review. Only approved proposals can be executed."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-left">
              <thead>
                <tr className="border-b border-paper-200 bg-paper-50/60">
                  {["Status", "Material", "Flow", "Quantity", "Evidence", "Updated", ""].map(
                    (heading) => (
                      <th
                        key={heading}
                        className="label-mono px-4 py-2.5 text-[8.5px] font-normal text-ink-400"
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {paged.map((proposal) => (
                  <tr key={proposal.id} className="row-hover border-b border-paper-200/70 last:border-0">
                    <td className="px-4 py-3 align-top">
                      <ProposalStatusBadge status={proposal.status} />
                      {proposal.is_demo ? (
                        <span className="mt-1 block font-mono text-[8px] tracking-wide text-ink-300 uppercase">
                          demo
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <p className="text-[12px] font-medium text-ink-900">
                        {proposal.material_name ?? "—"}
                      </p>
                      <p className="mt-0.5 font-mono text-[9px] text-ink-300">
                        {proposal.material_reference ?? "—"}
                      </p>
                    </td>
                    <td className="px-4 py-3 align-top text-[11px] text-ink-600">
                      {proposal.supplier_name ?? "—"}
                      <span className="mx-1.5 text-ink-300">→</span>
                      {proposal.consumer_name ?? "—"}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <p className="figure text-[12px] text-ink-900">
                        {formatQuantity(proposal.quantity, proposal.unit)}
                      </p>
                      {proposal.price_per_unit !== null ? (
                        <p className="mt-0.5 font-mono text-[9px] text-ink-300">
                          {proposal.price_per_unit} {proposal.currency}/{proposal.unit}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      {proposal.approved_at ? (
                        <Badge tone="forest" mono>
                          approved
                        </Badge>
                      ) : proposal.status === "in_progress" || proposal.status === "completed" ? (
                        <Badge tone="lime" mono>
                          executing
                        </Badge>
                      ) : (
                        <span className="font-mono text-[9px] text-ink-300">none</span>
                      )}
                      <p className="mt-1 text-[10px] text-ink-400">
                        {proposal.transaction_status
                          ? `transaction ${proposal.transaction_status}`
                          : "no transaction"}
                      </p>
                    </td>
                    <td className="px-4 py-3 align-top font-mono text-[9.5px] text-ink-400">
                      {formatDate(proposal.updated_at)}
                      <span className="mt-0.5 block text-[9px] text-ink-300">
                        {relativeTime(proposal.updated_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top text-right">
                      <Link
                        href={`/proposals/${proposal.id}`}
                        className="font-mono text-[9.5px] tracking-wide text-forest-700 uppercase hover:underline"
                      >
                        open
                      </Link>
                    </td>
                  </tr>
                                    ))}
                  </tbody>
                </table>
              </div>
            )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-paper-200 px-4 py-3">
          <p className="font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">
            Page {currentPage + 1} of {pageCount} · {visible.length} records
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage(currentPage - 1)}
              disabled={currentPage === 0}
              className="rounded-lg border border-paper-300 px-2.5 py-1 text-[10.5px] text-ink-600 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setPage(currentPage + 1)}
              disabled={currentPage >= pageCount - 1}
              className="rounded-lg border border-paper-300 px-2.5 py-1 text-[10.5px] text-ink-600 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      <Modal
        open={canCreate && creating}
        onClose={() => setCreating(false)}
        title="New draft proposal"
        description="Only screened supply/demand pairs can become proposals. The compatibility result is snapshotted; it cannot be overridden here."
        width="max-w-xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="rounded-lg border border-paper-300 px-3 py-1.5 text-[11.5px] text-ink-600 hover:bg-paper-100"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={create}
              disabled={pending || !form.opportunity_id || !form.quantity}
              className="rounded-lg bg-forest-800 px-3 py-1.5 text-[11.5px] font-medium text-paper-50 disabled:opacity-50"
            >
              {pending ? "Creating…" : "Create draft"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="block">
            <span className="label-mono text-[8.5px] text-ink-400">Screened opportunity *</span>
            <select
              value={form.opportunity_id}
              onChange={(event) =>
                setForm((previous) => ({ ...previous, opportunity_id: event.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
            >
              <option value="">Select an opportunity…</option>
              {available.map((opportunity) => (
                <option key={opportunity.id} value={opportunity.id}>
                  {opportunity.material.name} · {opportunity.supplier.name} →{" "}
                  {opportunity.consumer.name} ({opportunity.match_quantity} {opportunity.unit},{" "}
                  {opportunity.compatibility_status})
                </option>
              ))}
            </select>
          </label>

          {selected ? (
            <p className="rounded-lg border border-paper-200 bg-paper-50 px-3 py-2 text-[11px] leading-relaxed text-ink-500">
              Maximum screened quantity {formatQuantity(selected.match_quantity, selected.unit)} ·
              compatibility <span className="font-medium">{selected.compatibility_status}</span> ·
              score {selected.compatibility_score}/100
            </p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">Quantity *</span>
              <input
                type="number"
                step="0.001"
                value={form.quantity}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, quantity: event.target.value }))
                }
                className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
              />
            </label>
            <label className="block">
              <span className="label-mono text-[8.5px] text-ink-400">Price per unit (optional)</span>
              <input
                type="number"
                step="0.01"
                value={form.price}
                onChange={(event) =>
                  setForm((previous) => ({ ...previous, price: event.target.value }))
                }
                className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
              />
            </label>
          </div>

          <label className="block">
            <span className="label-mono text-[8.5px] text-ink-400">Notes</span>
            <textarea
              rows={2}
              value={form.notes}
              onChange={(event) =>
                setForm((previous) => ({ ...previous, notes: event.target.value }))
              }
              className="mt-1 w-full rounded-lg border border-paper-300 bg-[#fffdf8] px-2.5 py-2 text-[12px] text-ink-800"
            />
          </label>

          {error ? (
            <p className="rounded-lg border border-rust-500/30 bg-rust-500/10 px-3 py-2 text-[11.5px] leading-relaxed text-rust-500">
              {error}
            </p>
          ) : null}
        </div>
      </Modal>
    </>
  );
}
