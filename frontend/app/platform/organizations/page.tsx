import type { Metadata } from "next";
import Link from "next/link";

import { OrganizationRegister } from "@/components/platform/organization-register";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { PLATFORM_PERMISSION, canPlatform, platformHref, readParam } from "@/lib/platform";
import type { PlatformOrganizationRow } from "@/lib/platform-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Organisation register",
  description: "Platform-only register of LOOPMESH tenants and their lifecycle state.",
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 25;

export default async function PlatformOrganizationsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · tenants"
      title="Every organisation, one register."
      description="Search and filter the tenant estate, inspect operational metadata, and suspend or reactivate an organisation. Names, slugs, lifecycle state and membership counts only — never tenant business records."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.organizationsView)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="The organisation register needs platform.organizations.view"
          capability="platform.organizations.view"
          description="Your account is a platform operator without this capability. The API refuses the register for the same reason, so no records are fetched."
        />
      </>
    );
  }

  const params = await searchParams;
  const q = readParam(params, "q").slice(0, 120);
  const statusParam = readParam(params, "status");
  const status = statusParam === "active" || statusParam === "suspended" ? statusParam : "";
  const pageParam = Number.parseInt(readParam(params, "page") || "1", 10);
  const page = Number.isFinite(pageParam) && pageParam > 0 ? pageParam : 1;

  const response = await apiGet<Page<PlatformOrganizationRow>>(
    platformHref("/platform/organizations", { q, status, page, page_size: PAGE_SIZE }),
  );

  const canManage = canPlatform(user, PLATFORM_PERMISSION.organizationsManage);
  const filtered = Boolean(q || status);

  return (
    <>
      {header}

      <Panel>
        <PanelHeader
          eyebrow="Filters"
          title="Search the register"
          subtitle="Search matches organisation name, slug and city. Filters and page are part of the URL, so a view can be shared with another operator."
          action={
            <span className="font-mono text-[10px] text-ink-400">
              {canManage ? "lifecycle changes enabled" : "read-only"}
            </span>
          }
        />
        <form
          method="get"
          action="/platform/organizations"
          role="search"
          aria-label="Search organisations"
          className="flex flex-col gap-3 border-b border-paper-200 px-4 py-4 sm:flex-row sm:items-end sm:px-6"
        >
          <label className="block min-w-0 flex-1">
            <span className="label-mono text-[8.5px] text-ink-400">Search organisations</span>
            <input
              type="search"
              name="q"
              defaultValue={q}
              maxLength={120}
              placeholder="Name, slug or city"
              className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
            />
          </label>
          <label className="block sm:w-48">
            <span className="label-mono text-[8.5px] text-ink-400">Filter by status</span>
            <select
              name="status"
              defaultValue={status}
              className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </select>
          </label>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 transition-colors hover:bg-forest-800"
            >
              Apply
            </button>
            <Link
              href="/platform/organizations"
              className="h-9 rounded-lg border border-paper-300 px-3 text-[12px] leading-9 text-ink-600 hover:bg-paper-100"
            >
              Reset
            </Link>
          </div>
        </form>

        {!response.ok ? (
          <div className="px-4 py-4 sm:px-6">
            <DataUnavailable
              title="Organisation register unavailable"
              message={response.error}
              hint="The API scopes this register to platform operators; an empty screen is never substituted for a refusal."
            />
          </div>
        ) : response.data.items.length === 0 ? (
          <EmptyState
            title={filtered ? "No organisations match" : "No organisations yet"}
            description={
              filtered
                ? "No tenant matches this search and status combination. Clear the filters to see the whole register."
                : "The platform has no organisation records yet. They appear here as soon as the first tenant is created."
            }
          />
        ) : (
          <OrganizationRegister
            items={response.data.items}
            total={response.data.total}
            page={response.data.page}
            pageSize={response.data.page_size}
            hasMore={response.data.has_more}
            filters={{ q, status }}
          />
        )}
      </Panel>

      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        Suspension changes what a tenant can do, not what is stored. Deleting an organisation is not
        offered anywhere in the console or the API.
      </p>
    </>
  );
}
