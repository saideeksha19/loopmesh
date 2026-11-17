import { OpportunityExplorer } from "@/components/opportunities/opportunity-explorer";
import { InfoIcon } from "@/components/icons";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { DemoNotice } from "@/components/ui/demo-notice";
import { PageHeader } from "@/components/ui/page-header";
import { apiGet } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { Opportunity, Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OpportunitiesPage() {
  const response = await apiGet<Page<Opportunity>>("/opportunities?page_size=200");
  const items = response.ok ? response.data.items : [];
  const compatible = items.filter((item) => item.compatibility_status === "compatible").length;
  const conditional = items.filter((item) => item.compatibility_status === "conditional").length;

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Recovery opportunities · deterministic screening"
        title="Feasible recovery links"
        description="Each row is a supply/demand pair that cleared every blocking engineering rule. Expand a row to read the complete evidence trail — the score is arithmetic over nine weighted rules, not a model prediction."
        actions={
          response.ok ? (
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10px]">
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-paper-100/85">
                {formatNumber(response.data.total)} screened
              </span>
              <span className="rounded-full border border-lime-400/30 bg-lime-400/15 px-3 py-1.5 text-lime-200">
                {compatible} compatible
              </span>
              <span className="rounded-full border border-clay-500/30 bg-clay-500/15 px-3 py-1.5 text-clay-500">
                {conditional} conditional
              </span>
            </div>
          ) : null
        }
      />

      <div className="mb-4">
        <DemoNotice compact />
      </div>

      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-paper-300/70 bg-paper-50/90 px-4 py-3 shadow-[var(--shadow-soft)] backdrop-blur-sm">
        <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-forest-600" />
        <p className="text-[11.5px] leading-relaxed text-ink-500">
          An opportunity is a <span className="font-medium text-ink-700">screening result</span>, not a transaction. Gemini is never asked whether a material is safe: rule outcomes, threshold values and unknown-evidence handling are deterministic and reproducible. Pairs failing a blocking rule are excluded from this list.
        </p>
      </div>

      {response.ok ? (
        <OpportunityExplorer opportunities={items} />
      ) : (
        <DataUnavailable message={response.error} title="Opportunities unavailable" />
      )}
    </>
  );
}
