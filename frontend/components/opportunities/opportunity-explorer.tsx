"use client";

import { useMemo, useState } from "react";

import { ArrowRight, SearchIcon } from "@/components/icons";
import { Badge, CompatibilityBadge, RuleStatusDot } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatNumber, formatQuantity, titleCase } from "@/lib/format";
import type { Opportunity } from "@/lib/types";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "compatible", label: "Compatible" },
  { key: "conditional", label: "Conditional" },
  { key: "unverified", label: "Unverified" },
];

function ScoreRing({ score, status }: { score: number; status: string }) {
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, score)) / 100;
  const color =
    status === "compatible"
      ? "var(--color-forest-600)"
      : status === "conditional"
        ? "var(--color-clay-500)"
        : "var(--color-ink-300)";

  return (
    <div className="relative h-11 w-11 shrink-0">
      <svg viewBox="0 0 40 40" className="h-11 w-11 -rotate-90">
        <circle cx="20" cy="20" r={radius} fill="none" stroke="var(--color-paper-200)" strokeWidth="3" />
        <circle
          cx="20"
          cy="20"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${progress * circumference} ${circumference}`}
        />
      </svg>
      <span className="figure absolute inset-0 flex items-center justify-center text-[11px] font-medium text-ink-800">
        {score}
      </span>
    </div>
  );
}

function RuleRows({ opportunity }: { opportunity: Opportunity }) {
  const counts = opportunity.compatibility_rules.reduce<Record<string, number>>((acc, rule) => {
    acc[rule.status] = (acc[rule.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="border-t border-paper-200 bg-paper-50/60 px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-3 font-mono text-[9px] tracking-wide text-ink-400 uppercase">
        <span>{counts.pass ?? 0} passed</span>
        <span>{counts.warning ?? 0} advisory</span>
        <span>{counts.unknown ?? 0} unknown</span>
        <span>{counts.fail ?? 0} failed</span>
        <span className="ml-auto normal-case tracking-normal">
          deterministic rules v1 · weights total 100
        </span>
      </div>
      <div className="overflow-hidden rounded-lg border border-paper-200 bg-[#fffdf8]">
        <table className="w-full border-collapse text-left">
          <tbody>
            {opportunity.compatibility_rules.map((rule) => (
              <tr key={rule.rule_id} className="border-b border-paper-200/70 last:border-0">
                <td className="w-[92px] px-3 py-2 align-top font-mono text-[9.5px] tracking-wide text-ink-400">
                  {rule.rule_id}
                </td>
                <td className="w-[168px] px-2 py-2 align-top">
                  <span className="flex items-center gap-1.5 text-[11px] font-medium text-ink-700">
                    <RuleStatusDot status={rule.status} />
                    {rule.label}
                  </span>
                  <span className="mt-0.5 block font-mono text-[8.5px] tracking-wide text-ink-300 uppercase">
                    {rule.severity} · weight {rule.weight}
                  </span>
                </td>
                <td className="px-2 py-2 align-top text-[11px] leading-relaxed text-ink-500">
                  {rule.detail}
                  <span className="mt-1 block font-mono text-[9.5px] text-ink-300">
                    observed {rule.observed} · required {rule.required}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function OpportunityExplorer({ opportunities }: { opportunities: Opportunity[] }) {
  const [compatibility, setCompatibility] = useState("all");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(opportunities[0]?.id ?? null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return opportunities.filter((opportunity) => {
      if (compatibility !== "all" && opportunity.compatibility_status !== compatibility) return false;
      if (!needle) return true;
      return [
        opportunity.material.name,
        opportunity.material.reference_code,
        opportunity.demand.title,
        opportunity.supplier.name,
        opportunity.consumer.name,
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [opportunities, compatibility, query]);

  const counts = useMemo(() => {
    return opportunities.reduce<Record<string, number>>((acc, item) => {
      acc[item.compatibility_status] = (acc[item.compatibility_status] ?? 0) + 1;
      return acc;
    }, {});
  }, [opportunities]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border border-paper-300 bg-paper-50 p-0.5">
          {FILTERS.map((filter) => (
            <button
              key={filter.key}
              type="button"
              onClick={() => setCompatibility(filter.key)}
              className={[
                "rounded-md px-2.5 py-1.5 text-[11px] transition-colors",
                compatibility === filter.key
                  ? "bg-forest-900 text-paper-50"
                  : "text-ink-500 hover:text-ink-900",
              ].join(" ")}
            >
              {filter.label}
              <span className="ml-1.5 font-mono text-[9px] opacity-60">
                {filter.key === "all"
                  ? opportunities.length
                  : (counts[filter.key] ?? 0)}
              </span>
            </button>
          ))}
        </div>

        <div className="relative min-w-[210px] flex-1 sm:max-w-xs">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search material, demand or party"
            aria-label="Search opportunities"
            className="w-full rounded-lg border border-paper-300 bg-paper-50 py-2 pl-8 pr-2.5 text-[12px] outline-none placeholder:text-ink-300 focus:border-forest-600 focus:bg-white"
          />
        </div>

        <p className="ml-auto hidden font-mono text-[9.5px] text-ink-300 lg:block">
          incompatible pairs are filtered by the engine and never listed
        </p>
      </div>

      {filtered.length === 0 ? (
        <div className="panel">
          <EmptyState
            title="No opportunities in this view"
            description="The deterministic engine only persists pairs that clear every blocking rule. Adjust the filter or add demand coverage."
          />
        </div>
      ) : (
        <div className="panel divide-y divide-paper-200 overflow-hidden">
          {filtered.map((opportunity) => {
            const open = expanded === opportunity.id;
            return (
              <div key={opportunity.id}>
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : opportunity.id)}
                  aria-expanded={open}
                  className="row-hover flex w-full flex-wrap items-center gap-x-4 gap-y-3 px-4 py-4 text-left sm:px-5"
                >
                  <ScoreRing
                    score={opportunity.compatibility_score}
                    status={opportunity.compatibility_status}
                  />

                  <div className="min-w-[220px] flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[13px] font-medium text-ink-900">
                        {opportunity.material.name}
                      </p>
                      <span className="font-mono text-[9.5px] text-ink-300">
                        {opportunity.material.reference_code}
                      </span>
                      <CompatibilityBadge status={opportunity.compatibility_status} />
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500">
                      {opportunity.supplier.name}
                      <ArrowRight className="h-3 w-3 text-ink-300" />
                      {opportunity.consumer.name}
                    </p>
                    <p className="mt-1 text-[10.5px] text-ink-400">
                      for “{opportunity.demand.title}” · {titleCase(opportunity.material.category)}
                    </p>
                  </div>

                  <div className="flex items-center gap-6 sm:gap-8">
                    <div>
                      <p className="label-mono text-[8px] text-ink-400">Match</p>
                      <p className="figure mt-1 text-[12.5px] text-ink-900">
                        {formatQuantity(opportunity.match_quantity, opportunity.unit)}
                      </p>
                    </div>
                    <div>
                      <p className="label-mono text-[8px] text-ink-400">Distance</p>
                      <p className="figure mt-1 text-[12.5px] text-ink-900">
                        {opportunity.distance_km !== null
                          ? `${formatNumber(opportunity.distance_km, 1)} km`
                          : "unknown"}
                      </p>
                    </div>
                    <div className="hidden sm:block">
                      <p className="label-mono text-[8px] text-ink-400">Status</p>
                      <p className="mt-1 text-[11px] text-ink-600">
                        {titleCase(opportunity.status)}
                      </p>
                    </div>
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full border border-paper-300 text-[11px] text-ink-400 transition-transform ${
                        open ? "rotate-90" : ""
                      }`}
                      aria-hidden
                    >
                      ›
                    </span>
                  </div>
                </button>

                {open ? <RuleRows opportunity={opportunity} /> : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
