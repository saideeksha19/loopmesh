import { NetworkCanvas } from "@/components/network/network-canvas";
import { NetworkIcon } from "@/components/icons";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { DemoNotice } from "@/components/ui/demo-notice";
import { PageHeader } from "@/components/ui/page-header";
import { apiGet } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { NetworkGraph } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function NetworkPage() {
  const graph = await apiGet<NetworkGraph>("/network");

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Resource network · knowledge graph"
        title="Industrial symbiosis map"
        description="Organisations are nodes; material, water and energy flows are lanes. Hover or select to inspect relationships. Dashed lanes are screening hypotheses; animated confirmed lanes carry verified recovery transactions."
        actions={
          graph.ok ? (
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10px]">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-paper-100/85">
                {formatNumber(graph.data.summary.organizations)} nodes
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-paper-100/85">
                {formatNumber(graph.data.summary.potential_links)} lanes
              </span>
              <span className="rounded-full border border-lime-400/30 bg-lime-400/15 px-3 py-1.5 text-lime-200">
                {formatNumber(graph.data.summary.confirmed_links)} confirmed
              </span>
            </div>
          ) : (
            <span className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-mono text-[10px] text-paper-100/70">
              <NetworkIcon className="h-3.5 w-3.5" /> offline
            </span>
          )
        }
      />

      <div className="mb-4">
        <DemoNotice compact />
      </div>

      {graph.ok ? (
        <>
          <NetworkCanvas graph={graph.data} />
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="panel px-4 py-4 transition-premium">
              <p className="label-mono text-[8.5px] text-ink-400">Isolated organisations</p>
              <p className="figure mt-1.5 text-[22px] text-ink-900">{graph.data.summary.unlinked_organizations}</p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-ink-400">
                Nodes with no modelled lane. They signal missing supply, missing demand, or a specification gap.
              </p>
            </div>
            <div className="panel px-4 py-4 transition-premium">
              <p className="label-mono text-[8.5px] text-ink-400">Material streams represented</p>
              <p className="figure mt-1.5 text-[22px] text-ink-900">{graph.data.summary.total_material_streams}</p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-ink-400">
                Every stream belongs to exactly one organisation and one material category.
              </p>
            </div>
            <div className="panel px-4 py-4 transition-premium">
              <p className="label-mono text-[8.5px] text-ink-400">Flow interpretation</p>
              <p className="mt-1.5 text-[12px] font-medium text-ink-800">Energy · Water · Material lanes</p>
              <p className="mt-1 text-[10.5px] leading-relaxed text-ink-400">
                Lane colour is derived from the real stream category. Confirmed lanes require at least one verified recovery transaction.
              </p>
            </div>
          </div>
        </>
      ) : (
        <DataUnavailable message={graph.error} title="Resource network unavailable" />
      )}
    </>
  );
}
