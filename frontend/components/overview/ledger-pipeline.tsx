import type { LedgerStateSummary } from "@/lib/types";
import { formatNumber, formatQuantity } from "@/lib/format";

const STATE_LABELS: Record<string, string> = {
  proposed: "Proposed",
  accepted: "Accepted",
  transported: "Transported",
  verified: "Verified",
};

const STATE_NOTES: Record<string, string> = {
  proposed: "Offer submitted, no commitment",
  accepted: "Commercial acceptance recorded",
  transported: "Material dispatched or delivered",
  verified: "Evidence checked — counts as recovered",
};

export function LedgerPipeline({ states }: { states: LedgerStateSummary[] }) {
  const maxCount = Math.max(1, ...states.map((state) => state.count));

  return (
    <div className="px-5 py-4 sm:px-6">
      <div className="space-y-3.5">
        {states.map((state, idx) => {
          const primary = state.quantity_by_unit[0];
          const share = Math.max(4, Math.round((state.count / maxCount) * 100));
          const verified = state.counted_as_impact;
          return (
            <div key={state.state} className="group grid grid-cols-[96px_1fr_auto] items-center gap-3 animate-rise" style={{ animationDelay: `${idx * 40}ms` }}>
              <div>
                <p className={`text-[12px] font-medium ${verified ? "text-forest-700" : "text-ink-700"}`}>
                  {STATE_LABELS[state.state] ?? state.state}
                </p>
                <p className="mt-0.5 text-[10px] leading-tight text-ink-400">
                  {STATE_NOTES[state.state] ?? ""}
                </p>
              </div>

              <div className="h-7 overflow-hidden rounded-lg border border-paper-300/50 bg-paper-100/80">
                <div
                  className={[
                    "relative flex h-full items-center rounded-lg transition-all duration-700 ease-out",
                    verified
                      ? "bg-gradient-to-r from-lime-500/80 to-lime-400/70 shadow-[inset_0_0_0_1px_rgba(198,243,92,0.25)]"
                      : state.state === "transported"
                        ? "bg-forest-600/35"
                        : state.state === "accepted"
                          ? "bg-forest-600/22"
                          : "bg-forest-600/14",
                  ].join(" ")}
                  style={{ width: `${state.count === 0 ? 0 : share}%` }}
                >
                  {verified ? <span className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-white/20 to-transparent" aria-hidden /> : null}
                  <span className={`figure pl-2 text-[11px] ${verified ? "text-forest-950" : "text-forest-900/80"}`}>
                    {state.count}
                  </span>
                </div>
              </div>

              <div className="min-w-[88px] text-right">
                <p className="figure text-[11.5px] text-ink-700">
                  {primary ? formatQuantity(primary.quantity, primary.unit) : "—"}
                </p>
                {state.quantity_by_unit.length > 1 ? (
                  <p className="text-[9.5px] text-ink-300">
                    {formatNumber(state.quantity_by_unit.length)} units
                  </p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-4 border-t border-paper-200/80 pt-3 text-[10.5px] leading-relaxed text-ink-400">
        Only the verified state contributes to recovered material. Proposed, accepted and transported quantities remain pipeline until evidence is recorded.
      </p>
    </div>
  );
}
