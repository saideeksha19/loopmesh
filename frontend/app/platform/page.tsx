import type { Metadata } from "next";

import { PlatformOverview } from "@/components/platform/overview";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { apiGet } from "@/lib/api";
import { PLATFORM_PERMISSION, canPlatform } from "@/lib/platform";
import type { PlatformDashboard } from "@/lib/platform-types";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Platform overview",
  description: "Aggregate operational view across every LOOPMESH tenant.",
  robots: { index: false, follow: false },
};

export default async function PlatformOverviewPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · operations"
      title="The estate, not one tenant."
      description="Aggregate counts across every organisation, plus the privileged events an operator needs to notice. Individual tenant business records — materials, proposals, transactions, documents — are never exposed here."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.dashboard)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="The operator overview needs platform.dashboard.view"
          capability="platform.dashboard.view"
          description="Your account is a platform operator, but this particular capability is not granted. Ask another platform administrator to review your access; the API enforces the same check."
        />
      </>
    );
  }

  const response = await apiGet<PlatformDashboard>("/platform/dashboard");

  return (
    <>
      {header}
      {response.ok ? (
        <PlatformOverview data={response.data} />
      ) : (
        <DataUnavailable
          title="Platform metrics unavailable"
          message={response.error}
          hint="Counts are never simulated in the browser: this panel stays empty until the API answers."
        />
      )}
      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        Counts are grouped queries over the live database and are labelled with their window.
        Organisation names appear only where an operator must act on a specific record. Failed
        sign-ins are counted from authentication events; they are not attributed to a tenant
        because the login event does not carry one.
      </p>
    </>
  );
}
