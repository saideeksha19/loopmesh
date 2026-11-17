import { StageAccounting } from "@/components/overview/stage-accounting";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { formatDate, formatNumber, formatQuantity, titleCase } from "@/lib/format";
import type { LedgerReport } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATE_TONE: Record<string, "lime" | "forest" | "neutral" | "outline"> = {
  verified: "lime",
  transported: "forest",
  accepted: "neutral",
  proposed: "outline",
};

export default async function LedgerPage() {
  const response = await apiGet<LedgerReport>("/ledger");

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Circular impact ledger · evidence accounting"
        title="Only verified mass counts."
        description="The ledger separates what was proposed, accepted and moved from what was actually verified. Totals are computed from recorded evidence, never from intentions."
      />

      {!response.ok ? (
        <DataUnavailable message={response.error} title="Ledger unavailable" />
      ) : (
        <>
          <div className="panel mb-4 overflow-hidden">
            <div className="relative grid gap-5 bg-[linear-gradient(135deg,#10291a_0%,#1e3529_45%,#2c4434_100%)] px-5 py-6 text-paper-100 sm:px-6 lg:grid-cols-[1.2fr_1fr]">
              <div className="tech-grid-dark absolute inset-0 opacity-45" aria-hidden />
              <div className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-lime-400/10 blur-3xl" aria-hidden />
              <div className="relative">
                <p className="label-mono text-[9px] text-lime-300/90">Verified recovered material</p>
                <p className="figure mt-2.5 text-[38px] leading-none text-paper-50">
                  {response.data.verified_recovered.length
                    ? formatQuantity(
                        response.data.verified_recovered[0].quantity,
                        response.data.verified_recovered[0].unit,
                      )
                    : "0"}
                </p>
                <p className="mt-3 max-w-md text-[11.5px] leading-relaxed text-paper-100/70">
                  {response.data.accounting_rule}
                </p>
              </div>
              <div className="relative rounded-xl border border-white/10 bg-white/[0.05] px-4 py-4 backdrop-blur-sm">
                <p className="label-mono text-[8.5px] text-paper-100/60">Pipeline — explicitly not impact</p>
                <p className="figure mt-1.5 text-[22px] text-paper-50">
                  {response.data.proposed_pipeline.length
                    ? formatQuantity(
                        response.data.proposed_pipeline[0].quantity,
                        response.data.proposed_pipeline[0].unit,
                      )
                    : "0"}
                </p>
                <p className="mt-1.5 text-[10.5px] leading-relaxed text-paper-100/65">
                  Proposed, accepted or in transit. Excluded from recovered totals until a verification record exists.
                </p>
              </div>
            </div>

            <div className="border-t border-paper-200/80">
              <div className="border-b border-paper-200/80 px-4 py-2.5">
                <p className="label-mono text-[8.5px] text-ink-400">Lifecycle accounting · one stage per record</p>
              </div>
              <StageAccounting stages={response.data.stages} />
            </div>

            <div className="grid divide-y divide-paper-200/80 border-t border-paper-200/80 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
              {response.data.states.map((state) => (
                <div key={state.state} className="px-4 py-3.5 transition-premium hover:bg-paper-100/40">
                  <div className="flex items-center justify-between">
                    <p className="label-mono text-[8.5px] text-ink-400">{state.state}</p>
                    {state.counted_as_impact ? (
                      <span className="h-1.5 w-1.5 rounded-full bg-lime-500 shadow-[0_0_8px_rgba(198,243,92,0.5)]" />
                    ) : (
                      <span className="h-1.5 w-1.5 rounded-full bg-paper-300" />
                    )}
                  </div>
                  <p className="figure mt-1.5 text-[18px] text-ink-900">{state.count}</p>
                  <p className="mt-0.5 text-[10.5px] text-ink-400">
                    {state.quantity_by_unit.length
                      ? formatQuantity(state.quantity_by_unit[0].quantity, state.quantity_by_unit[0].unit)
                      : "no quantity"}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <Panel>
            <PanelHeader
              eyebrow="Recovery records"
              title="Ledger entries"
              subtitle="Each entry is a proposal with its current business state. Verification evidence is shown where it exists."
              action={
                <Badge tone={response.data.contains_demo_data ? "muted" : "neutral"} mono>
                  {response.data.contains_demo_data ? "demo data" : "operational"}
                </Badge>
              }
            />
            {response.data.entries.length === 0 ? (
              <EmptyState
                title="No ledger entries yet"
                description="Once a proposal is submitted it appears here as pipeline. Verification evidence is required before it can contribute to recovered totals."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[920px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-paper-200/80 bg-paper-50/70">
                      {["State", "Material", "Flow", "Quantity", "Verification", "Updated"].map((heading) => (
                        <th key={heading} className="label-mono px-4 py-2.5 text-[8.5px] font-normal text-ink-400">
                          {heading}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {response.data.entries.map((entry) => (
                      <tr key={`${entry.proposal_id}-${entry.transaction_id ?? "proposal"}`} className="border-b border-paper-200/70 last:border-0 transition-premium hover:bg-paper-100/40">
                        <td className="px-4 py-3 align-top">
                          <Badge tone={STATE_TONE[entry.state] ?? "outline"} mono>{entry.state}</Badge>
                          {entry.is_verified ? (
                            <p className="mt-1 font-mono text-[9px] uppercase tracking-wide text-lime-600">counted as impact</p>
                          ) : (
                            <p className="mt-1 font-mono text-[9px] uppercase tracking-wide text-ink-400">{titleCase(entry.stage.replace(/_/g, " "))}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <p className="text-[12px] font-medium text-ink-800">{entry.material_name}</p>
                          <p className="mt-0.5 font-mono text-[9.5px] text-ink-400">{entry.material_reference ?? entry.proposal_id}</p>
                          <p className="mt-0.5 font-mono text-[9px] text-ink-300">{titleCase(entry.category)}</p>
                        </td>
                        <td className="px-4 py-3 align-top text-[11.5px] text-ink-600">
                          <p>{entry.supplier}</p>
                          <p className="text-ink-400">→ {entry.consumer}</p>
                          {typeof entry.transport_distance_km === "number" ? (
                            <p className="mt-0.5 font-mono text-[9px] text-ink-400">{formatNumber(entry.transport_distance_km)} km</p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <p className="figure text-[12px] text-ink-800">{formatQuantity(entry.quantity, entry.unit)}</p>
                          {entry.verified_quantity != null ? (
                            <p className="mt-0.5 font-mono text-[9.5px] text-lime-700">
                              Verified {formatQuantity(entry.verified_quantity, entry.unit)}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 align-top text-[11px] leading-relaxed text-ink-500">
                          {entry.verification_method || entry.verified_at ? (
                            <>
                              <p className="font-medium text-ink-700">{entry.verification_method ? titleCase(entry.verification_method.replace(/_/g, " ")) : "Verified"}</p>
                              {entry.verified_at ? <p className="mt-0.5 text-ink-400">{formatDate(entry.verified_at)}</p> : null}
                            </>
                          ) : (
                            <span className="text-ink-300">No verification evidence</span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top font-mono text-[10px] text-ink-400">
                          {formatDate(entry.last_updated ?? entry.proposed_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </>
  );
}
