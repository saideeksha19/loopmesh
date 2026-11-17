"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { TransactionStatusBadge } from "@/components/workflow/status-badge";
import { formatDate, formatNumber, formatQuantity, relativeTime } from "@/lib/format";
import type { TransactionSummary } from "@/lib/workflow-types";

const FILTERS = [
  { key: "all", label: "All", states: [] as string[] },
  { key: "open", label: "Open", states: ["created", "in_progress"] },
  { key: "transferred", label: "Awaiting verification", states: ["transferred"] },
  { key: "verified", label: "Verified", states: ["verified"] },
  { key: "closed", label: "Rejected / cancelled", states: ["rejected", "cancelled", "failed"] },
];

export function TransactionWorkspace({ transactions }: { transactions: TransactionSummary[] }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const visible = useMemo(() => {
    const active = FILTERS.find((item) => item.key === filter) ?? FILTERS[0];
    const needle = query.trim().toLowerCase();
    return transactions.filter((transaction) => {
      if (active.states.length && !active.states.includes(transaction.status)) return false;
      if (!needle) return true;
      return [
        transaction.material_name,
        transaction.material_reference,
        transaction.transfer_reference,
        transaction.source_organization_name,
        transaction.destination_organization_name,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [transactions, filter, query]);

  const pageSize = 15;
  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const paged = visible.slice(currentPage * pageSize, currentPage * pageSize + pageSize);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {FILTERS.map((item) => {
          const count = item.states.length
            ? transactions.filter((transaction) => item.states.includes(transaction.status)).length
            : transactions.length;
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
          aria-label="Search transactions"
        />
      </div>

      <div className="panel overflow-hidden">
        {visible.length === 0 ? (
          <EmptyState
            title="No transactions in this view"
            description="Transactions are created from approved proposals. Recording a transfer and verifying it are separate steps with separate authority."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] border-collapse text-left">
              <thead>
                <tr className="border-b border-paper-200 bg-paper-50/60">
                  {["Status", "Material", "Flow", "Quantities", "Transfer", "Updated", ""].map(
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
                {paged.map((transaction) => (
                  <tr
                    key={transaction.id}
                    className="row-hover border-b border-paper-200/70 last:border-0"
                  >
                    <td className="px-4 py-3 align-top">
                      <TransactionStatusBadge status={transaction.status} />
                      {transaction.is_demo ? (
                        <span className="mt-1 block font-mono text-[8px] tracking-wide text-ink-300 uppercase">
                          demo
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <p className="text-[12px] font-medium text-ink-900">
                        {transaction.material_name ?? "—"}
                      </p>
                      <p className="mt-0.5 font-mono text-[9px] text-ink-300">
                        {transaction.material_reference ?? "—"}
                      </p>
                    </td>
                    <td className="px-4 py-3 align-top text-[11px] text-ink-600">
                      {transaction.source_organization_name ?? "—"}
                      <span className="mx-1.5 text-ink-300">→</span>
                      {transaction.destination_organization_name ?? "—"}
                      {transaction.transport_distance_km !== null ? (
                        <span className="mt-0.5 block font-mono text-[9px] text-ink-300">
                          {formatNumber(transaction.transport_distance_km, 1)} km
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <p className="figure text-[11.5px] text-ink-800">
                        {transaction.transferred_quantity !== null
                          ? formatQuantity(transaction.transferred_quantity, transaction.unit)
                          : `contracted ${formatQuantity(
                              transaction.accepted_quantity ?? 0,
                              transaction.unit,
                            )}`}
                      </p>
                      {transaction.verified_quantity !== null ? (
                        <p className="mt-0.5 font-mono text-[9px] text-forest-700">
                          verified {formatQuantity(transaction.verified_quantity, transaction.unit)}
                        </p>
                      ) : (
                        <p className="mt-0.5 font-mono text-[9px] text-ink-300">not verified</p>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top text-[10.5px] text-ink-500">
                      {transaction.transfer_reference ?? "—"}
                      <span className="mt-0.5 block font-mono text-[9px] text-ink-300">
                        {formatDate(transaction.transferred_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top font-mono text-[9.5px] text-ink-400">
                      {formatDate(transaction.created_at)}
                      <span className="mt-0.5 block text-[9px] text-ink-300">
                        {relativeTime(transaction.created_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top text-right">
                      <Link
                        href={`/transactions/${transaction.id}`}
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
    </>
  );
}
