import type { Metadata } from "next";
import Link from "next/link";

import { ApprovalList } from "@/components/platform/approval-list";
import { ApprovalRequestForm } from "@/components/platform/approval-request-form";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { PLATFORM_PERMISSION, canPlatform, platformHref, readParam } from "@/lib/platform";
import type {
  PlatformApproval,
  PlatformOrganizationRow,
} from "@/lib/platform-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Platform approvals",
  description: "Two-person approval requests for tenant lifecycle changes.",
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 20;
const STATUSES = ["pending", "approved", "executed", "rejected", "cancelled", "expired"] as const;

export default async function PlatformApprovalsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · governance"
      title="Two people, one irreversible change."
      description="Suspend or reactivate a tenant only through a request that a different operator approves. The request records its target, action and reason; changing any of them invalidates it."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.approvalsView)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="Approvals need platform.approvals.view"
          capability="platform.approvals.view"
          description="Your account is a platform operator without this capability. The API refuses the approval list and every decision route as well."
        />
      </>
    );
  }

  const params = await searchParams;
  const status = readParam(params, "status");
  const validStatus = (STATUSES as readonly string[]).includes(status) ? status : "";
  const organizationId = readParam(params, "organization_id").slice(0, 36);
  const pageParam = Number.parseInt(readParam(params, "page") || "1", 10);
  const page = Number.isFinite(pageParam) && pageParam > 0 ? pageParam : 1;

  const canRequest =
    canPlatform(user, PLATFORM_PERMISSION.approvalsRequest) &&
    canPlatform(user, PLATFORM_PERMISSION.organizationsManage);

  const [response, organisationResponse] = await Promise.all([
    apiGet<Page<PlatformApproval>>(
      platformHref("/platform/approvals", {
        status: validStatus,
        organization_id: organizationId,
        page,
        page_size: PAGE_SIZE,
      }),
    ),
    canRequest
      ? apiGet<Page<PlatformOrganizationRow>>("/platform/organizations?page_size=200")
      : Promise.resolve(null),
  ]);

  const organisations = organisationResponse?.ok ? organisationResponse.data.items : [];

  return (
    <>
      {header}

      <Panel className="mb-4">
        <PanelHeader
          eyebrow="Request"
          title="Ask a second operator"
          subtitle="Creating a request changes nothing yet. The tenant keeps its current state until an approved request is executed."
        />
        <ApprovalRequestForm organizations={organisations} canRequest={canRequest} />
      </Panel>

      <Panel>
        <PanelHeader
          eyebrow="Queue"
          title="Approval requests"
          subtitle={
            organizationId
              ? `Filtered to one organisation. Newest first; pending requests expire automatically.`
              : "Newest first. Pending requests expire automatically; expired, rejected and cancelled requests cannot be revived."
          }
          action={
            <Badge tone="muted" mono>
              {response.ok ? `${response.data.total} total` : "unavailable"}
            </Badge>
          }
        />
        <div className="flex flex-wrap gap-1.5 border-b border-paper-200 px-4 py-3 sm:px-6">
          <Link
            href={platformHref("/platform/approvals", { organization_id: organizationId })}
            className={[
              "rounded-lg px-2.5 py-1.5 text-[11px]",
              validStatus ? "text-ink-500 hover:bg-paper-100" : "bg-forest-900 text-lime-300",
            ].join(" ")}
          >
            All
          </Link>
          {STATUSES.map((candidate) => (
            <Link
              key={candidate}
              href={platformHref("/platform/approvals", {
                status: candidate,
                organization_id: organizationId,
              })}
              className={[
                "rounded-lg px-2.5 py-1.5 text-[11px] capitalize",
                validStatus === candidate
                  ? "bg-forest-900 text-lime-300"
                  : "text-ink-500 hover:bg-paper-100",
              ].join(" ")}
            >
              {candidate}
            </Link>
          ))}
        </div>

        {!response.ok ? (
          <div className="px-4 py-4 sm:px-6">
            <DataUnavailable
              title="Approval queue unavailable"
              message={response.error}
              hint="The console shows no requests rather than inventing a queue when the API refuses or cannot answer."
            />
          </div>
        ) : (
          <>
            <ApprovalList items={response.data.items} />
            <div className="flex items-center justify-between gap-2 border-t border-paper-200 px-4 py-3 sm:px-6">
              <p className="font-mono text-[10px] text-ink-400">
                page {response.data.page} · {response.data.page_size} per page
              </p>
              <div className="flex items-center gap-2">
                <Link
                  href={platformHref("/platform/approvals", {
                    status: validStatus,
                    organization_id: organizationId,
                    page: page - 1,
                  })}
                  aria-disabled={page <= 1}
                  className={[
                    "rounded-lg border px-2.5 py-1.5 text-[11px]",
                    page <= 1
                      ? "pointer-events-none border-paper-200 text-ink-300"
                      : "border-paper-300 bg-paper-50 text-ink-600 hover:bg-paper-100",
                  ].join(" ")}
                >
                  ← Previous
                </Link>
                <Link
                  href={platformHref("/platform/approvals", {
                    status: validStatus,
                    organization_id: organizationId,
                    page: page + 1,
                  })}
                  aria-disabled={!response.data.has_more}
                  className={[
                    "rounded-lg border px-2.5 py-1.5 text-[11px]",
                    !response.data.has_more
                      ? "pointer-events-none border-paper-200 text-ink-300"
                      : "border-paper-300 bg-paper-50 text-ink-600 hover:bg-paper-100",
                  ].join(" ")}
                >
                  Next →
                </Link>
              </div>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}
