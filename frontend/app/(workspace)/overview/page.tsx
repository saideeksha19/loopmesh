import Link from "next/link";

import { ActivityFeed } from "@/components/overview/activity-feed";
import { CategoryMix } from "@/components/overview/category-mix";
import { EngineStrip } from "@/components/overview/engine-strip";
import { LedgerPipeline } from "@/components/overview/ledger-pipeline";
import { NetworkPreview } from "@/components/overview/network-preview";
import { StageAccounting } from "@/components/overview/stage-accounting";
import {
  ArrowUpRight,
  LedgerIcon,
  MaterialIcon,
  NetworkIcon,
  OpportunityIcon,
  OverviewIcon,
} from "@/components/icons";
import { DemoNotice } from "@/components/ui/demo-notice";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { StatCard } from "@/components/ui/stat-card";
import { apiGet } from "@/lib/api";
import { formatNumber, formatQuantity, primaryQuantity, relativeTime } from "@/lib/format";
import type { LedgerReport, NetworkGraph, OverviewStats } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [overview, network, ledger] = await Promise.all([
    apiGet<OverviewStats>("/overview"),
    apiGet<NetworkGraph>("/network"),
    apiGet<LedgerReport>("/ledger"),
  ]);

  if (!overview.ok) {
    return (
      <>
        <PageHeader
          cinematic
          eyebrow="Industrial resource intelligence"
          title="Operational command view unavailable"
          description="Live dashboard data could not be loaded. No metrics are simulated."
        />
        <DataUnavailable message={overview.error} />
      </>
    );
  }

  const stats = overview.data;
  const verified = primaryQuantity(stats.ledger.verified_recovered);
  const pipeline = primaryQuantity(stats.ledger.proposed_pipeline);
  const conditional =
    stats.opportunities.by_compatibility.find((item) => item.key === "conditional")?.count ?? 0;
  const unverified =
    stats.opportunities.by_compatibility.find((item) => item.key === "unverified")?.count ?? 0;
  const confirmedLinks = network.ok ? network.data.edges.filter((e) => e.status === "confirmed") : [];
  const confirmedCount = confirmedLinks.length;
  const confirmedTx = confirmedLinks.reduce((sum, e) => sum + e.confirmed_transactions, 0);

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Industrial intelligence operating system"
        title={
          <>
            Resource recovery,
            <br className="hidden sm:block" /> orchestrated with evidence.
          </>
        }
        description="LOOPMESH unifies material intelligence, deterministic compatibility screening and verified recovery accounting into one operational view. Every figure below is sourced from live platform data."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full border border-lime-400/25 bg-lime-400/10 px-3 py-1.5 font-mono text-[9.5px] tracking-wider text-lime-200 uppercase shadow-[0_0_0_1px_rgba(198,243,92,0.05)]">
              <span className="h-1.5 w-1.5 rounded-full bg-lime-400 shadow-[0_0_10px_rgba(198,243,92,0.8)]" />
              {stats.data_mode === "demo" ? "Demo cluster · identified" : "Operational data"}
            </span>
            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 font-mono text-[9.5px] text-paper-100/80">
              updated {relativeTime(stats.generated_at)}
            </span>
          </div>
        }
      >
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur-sm">
            <p className="label-mono text-[8.5px] text-paper-100/60">Verified recovery (real)</p>
            <p className="figure mt-1.5 text-[22px] text-paper-50">
              {verified.formatted} <span className="text-[11px] font-sans text-paper-100/60">{verified.note ?? ""}</span>
            </p>
            <p className="mt-1 text-[10.5px] text-paper-100/55">Evidence-checked mass only.</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur-sm">
            <p className="label-mono text-[8.5px] text-paper-100/60">Exchange network</p>
            <p className="figure mt-1.5 text-[22px] text-paper-50">
              {formatNumber(stats.network.confirmed_links)} <span className="text-[11px] font-sans text-paper-100/60">confirmed</span>
            </p>
            <p className="mt-1 text-[10.5px] text-paper-100/55">
              {formatNumber(stats.network.potential_links)} modelled lanes · {formatNumber(confirmedTx)} verified transactions
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur-sm">
            <p className="label-mono text-[8.5px] text-paper-100/60">Pipeline (not impact)</p>
            <p className="figure mt-1.5 text-[22px] text-paper-50">
              {pipeline.formatted} <span className="text-[11px] font-sans text-paper-100/60">{pipeline.note ?? ""}</span>
            </p>
            <p className="mt-1 text-[10.5px] text-paper-100/55">Awaiting verification evidence.</p>
          </div>
        </div>
      </PageHeader>

      <DemoNotice />
      <div className="mt-4">
        <EngineStrip />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label="Organizations"
          value={formatNumber(stats.organizations.total)}
          icon={<NetworkIcon className="h-4 w-4" />}
          meta={`${formatNumber(stats.organizations.suppliers)} supplying · ${formatNumber(stats.organizations.consumers)} consuming`}
          delay={0}
        />
        <StatCard
          label="Material streams"
          value={formatNumber(stats.materials.total)}
          icon={<MaterialIcon className="h-4 w-4" />}
          meta={`${formatNumber(stats.materials.available)} available for matching`}
          delay={50}
        />
        <StatCard
          label="Recovery opportunities"
          value={formatNumber(stats.opportunities.total)}
          icon={<OpportunityIcon className="h-4 w-4" />}
          meta={`${formatNumber(conditional)} conditional · ${formatNumber(unverified)} awaiting evidence`}
          delay={100}
        />
        <StatCard
          label="Pending proposals"
          value={formatNumber(stats.opportunities.pending_proposals)}
          icon={<OverviewIcon className="h-4 w-4" />}
          meta="Submitted or under review"
          delay={150}
        />
        <StatCard
          label="Verified recovered"
          value={verified.formatted}
          unit={verified.note ?? undefined}
          icon={<LedgerIcon className="h-4 w-4" />}
          accent
          meta="Evidence-checked mass only. Pipeline excluded."
          delay={200}
        />
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-[1.65fr_1fr]">
        <div className="space-y-4">
          <Panel className="overflow-hidden">
            <PanelHeader
              eyebrow="Interactive resource ecosystem"
              title="Industrial resource network"
              subtitle="Live organisation nodes and material lanes. Hover or select a node for details. Confirmed lanes require verified transactions."
              action={
                <Link
                  href="/network"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-paper-300/70 bg-paper-50 px-3 py-1.5 text-[11px] font-medium text-ink-700 transition-premium hover:border-forest-600/30 hover:bg-paper-100"
                >
                  Open graph <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              }
            />
            <div className="grid gap-0 lg:grid-cols-[1.45fr_0.9fr]">
              <div className="relative min-h-[360px] px-3 py-3 sm:min-h-[420px]">
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(198,243,92,0.08),transparent_45%),radial-gradient(ellipse_at_80%_70%,rgba(79,168,154,0.08),transparent_40%)]" aria-hidden />
                {network.ok ? (
                  <NetworkPreview nodes={network.data.nodes} edges={network.data.edges} />
                ) : (
                  <p className="px-3 py-16 text-center text-[12px] text-ink-400">Network data unavailable.</p>
                )}
              </div>
              <div className="flex flex-col border-t border-paper-200/80 lg:border-l lg:border-t-0">
                <dl className="grid grid-cols-2 gap-px bg-paper-200/70">
                  {[
                    { label: "Organisations", value: formatNumber(stats.network.organizations) },
                    { label: "Modelled lanes", value: formatNumber(stats.network.potential_links) },
                    { label: "Confirmed lanes", value: formatNumber(stats.network.confirmed_links) },
                    {
                      label: "Isolated nodes",
                      value: formatNumber(network.ok ? network.data.summary.unlinked_organizations : 0),
                    },
                  ].map((item) => (
                    <div key={item.label} className="bg-paper-50/95 px-4 py-4">
                      <dt className="label-mono text-[8.5px] text-ink-400">{item.label}</dt>
                      <dd className="figure mt-2 text-[22px] text-ink-900">{item.value}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex-1 space-y-3 px-4 py-4">
                  <div className="rounded-xl border border-paper-200/80 bg-paper-100/60 p-3">
                    <p className="label-mono text-[8.5px] text-ink-400">Flow legend (real categories)</p>
                    <div className="mt-2 space-y-1.5 font-mono text-[10px] text-ink-600">
                      <div className="flex items-center gap-2"><span className="h-1.5 w-5 rounded-full" style={{ background: "var(--color-flow-energy)" }} /> Energy flows · lime</div>
                      <div className="flex items-center gap-2"><span className="h-1.5 w-5 rounded-full" style={{ background: "var(--color-flow-water)" }} /> Water flows · teal-sage</div>
                      <div className="flex items-center gap-2"><span className="h-1.5 w-5 rounded-full" style={{ background: "var(--color-flow-material)" }} /> Material flows · amber-lime</div>
                    </div>
                  </div>
                  <div className="rounded-xl border border-paper-200/80 bg-paper-50 p-3">
                    <p className="label-mono text-[8.5px] text-ink-400">Confirmed exchange activity</p>
                    <p className="mt-1.5 text-[12px] text-ink-700">
                      <span className="figure text-[16px] text-ink-900">{formatNumber(confirmedCount)}</span> confirmed lanes · <span className="figure text-[16px] text-ink-900">{formatNumber(confirmedTx)}</span> verified transactions
                    </p>
                    <p className="mt-1 text-[10.5px] leading-relaxed text-ink-500">Derived from verified transaction records on the live network.</p>
                  </div>
                </div>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader
              eyebrow="Circular impact ledger"
              title="Recovery pipeline"
              subtitle="Auditable lifecycle states. Only verified mass counts as impact."
              action={
                <Link
                  href="/ledger"
                  className="inline-flex items-center gap-1.5 text-[11px] font-medium text-forest-700 transition-colors hover:text-forest-900"
                >
                  Inspect ledger <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              }
            />
            <LedgerPipeline states={stats.ledger.states} />
            <div className="border-t border-paper-200/80">
              <div className="border-b border-paper-200/80 px-5 py-2.5 sm:px-6">
                <p className="label-mono text-[8.5px] text-ink-400">Lifecycle accounting · one bucket per record, never double counted</p>
              </div>
              <StageAccounting stages={stats.ledger.stages} />
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader eyebrow="Material DNA" title="Material mix" subtitle="Streams by category (real inventory)" />
            <CategoryMix categories={stats.materials.by_category} total={stats.materials.total} />
          </Panel>

          <Panel>
            <PanelHeader eyebrow="Audit journal" title="Recent activity" subtitle="Every mutation is recorded" />
            <ActivityFeed events={stats.recent_activity} />
          </Panel>

          <div className="panel px-5 py-4">
            <p className="label-mono text-[8.5px] text-ink-400">Pipeline mass, not impact</p>
            <p className="figure mt-2 text-[20px] text-ink-800">
              {pipeline.formatted} <span className="text-[11px] font-sans text-ink-400">{pipeline.note ?? ""}</span>
            </p>
            <p className="mt-1.5 text-[10.5px] leading-relaxed text-ink-400">
              Proposed, accepted or transported quantities remain excluded from recovered totals until verification evidence is attached.
            </p>
          </div>
        </div>
      </div>

      {ledger.ok ? null : (
        <p className="mt-3 text-[10.5px] text-ink-400">
          Ledger detail endpoint unavailable — totals above come from the overview aggregate.
        </p>
      )}
    </>
  );
}
