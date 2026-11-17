import type { Metadata } from "next";

import { HealthTable } from "@/components/platform/health-table";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { PLATFORM_PERMISSION, canPlatform, platformHref, readParam } from "@/lib/platform";
import type { PlatformTenantHealth } from "@/lib/platform-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Tenant health",
  description: "Bounded operational health signals for every LOOPMESH tenant.",
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 25;

export default async function PlatformHealthPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · tenant health"
      title="Operational signals, honestly labelled."
      description="Three checks the platform can verify from records — tenant state, membership presence and an active administrator — plus bounded windows of administrative, security and authentication activity."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.health)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="Tenant health needs platform.health.view"
          capability="platform.health.view"
          description="Your account is a platform operator without this capability, so no health data is fetched."
        />
      </>
    );
  }

  const params = await searchParams;
  const pageParam = Number.parseInt(readParam(params, "page") || "1", 10);
  const page = Number.isFinite(pageParam) && pageParam > 0 ? pageParam : 1;

  const response = await apiGet<Page<PlatformTenantHealth>>(
    platformHref("/platform/health", { page, page_size: PAGE_SIZE }),
  );

  return (
    <>
      {header}

      <Panel>
        <PanelHeader
          eyebrow="Bounded view"
          title="Tenants and their signals"
          subtitle="Counts come from grouped queries limited to this page of tenants; no unbounded scan is performed. An empty signal is a real zero."
        />
        {!response.ok ? (
          <div className="px-4 py-4 sm:px-6">
            <DataUnavailable title="Tenant health unavailable" message={response.error} />
          </div>
        ) : response.data.items.length === 0 ? (
          <EmptyState
            title="No tenants to check"
            description="Health rows appear once the platform has organisation records."
          />
        ) : (
          <HealthTable
            items={response.data.items}
            total={response.data.total}
            page={response.data.page}
            pageSize={response.data.page_size}
            hasMore={response.data.has_more}
          />
        )}
      </Panel>

      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        “Operational” means the three listed checks passed — nothing more. Authentication failures
        are attributed through the account&apos;s membership because a sign-in event is not
        tenant-scoped; an account with memberships in several tenants is counted in each. Pending
        invitations exclude expired ones. Health data is operational metadata, never tenant business
        content or credentials.
      </p>
    </>
  );
}
