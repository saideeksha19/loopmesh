import { formatQuantity } from "@/lib/format";
import type { LedgerStageSummary } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  draft: "Draft proposals",
  submitted: "Submitted proposals",
  approved: "Approved proposals",
  in_progress: "In-progress transactions",
  completed_unverified: "Transferred, unverified",
  verified: "Verified recovered",
  rejected_cancelled: "Rejected / cancelled",
};

const STAGE_NOTES: Record<string, string> = {
  draft: "Not yet offered to the counterparty",
  submitted: "Awaiting review by the receiving organisation",
  approved: "Contract agreed, execution not started",
  in_progress: "Transaction opened, transfer not recorded",
  completed_unverified: "Material moved — evidence outstanding",
  verified: "Evidence checked — counts as recovered",
  rejected_cancelled: "Closed without recovery",
};

/**
 * One record belongs to exactly one stage, so these totals never double count
 * and never overlap with `verified_recovered`.
 */
export function StageAccounting({ stages }: { stages: LedgerStageSummary[] }) {
  return (
    <div className="grid divide-y divide-paper-200/80 sm:grid-cols-2 lg:grid-cols-4 lg:divide-y-0">
      {stages.map((stage) => {
        const total = stage.quantity_by_unit[0];
        return (
          <div key={stage.stage} className="px-4 py-3.5 transition-premium hover:bg-paper-100/40">
            <div className="flex items-center justify-between gap-2">
              <p className="label-mono text-[8.5px] text-ink-400">
                {STAGE_LABELS[stage.stage] ?? stage.stage}
              </p>
              {stage.counted_as_impact ? (
                <span className="h-1.5 w-1.5 rounded-full bg-lime-500 shadow-[0_0_8px_rgba(198,243,92,0.5)]" aria-hidden />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-paper-300" aria-hidden />
              )}
            </div>
            <p className="figure mt-1.5 text-[18px] text-ink-900">{stage.count}</p>
            <p className="mt-0.5 text-[10.5px] text-ink-500">
              {total ? formatQuantity(total.quantity, total.unit) : "no quantity"}
            </p>
            <p className="mt-1 text-[9.5px] leading-relaxed text-ink-300">
              {STAGE_NOTES[stage.stage] ?? ""}
            </p>
          </div>
        );
      })}
    </div>
  );
}
