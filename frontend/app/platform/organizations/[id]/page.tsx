import type { Metadata } from "next";
import Link from "next/link";

import { OrganizationStatus } from "@/components/platform/organization-status";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { formatDate, relativeTime, sectorLabel } from "@/lib/format";
import {
  PLATFORM_PERMISSION,
  SUSPENSION_EFFECTS,
  canPlatform,
  healthStateLabel,
  healthStateTone,
  healthWarningCopy,
} from "@/lib/platform";
import type { PlatformOrganizationDetail } from "@/lib/platform-types";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Organisation detail",
  description: "Operational metadata and lifecycle administration for one LOOPMESH tenant.",
  robots: { index: false, follow: false },
};

function Count({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div>
      <p className="label-mono text-[8.5px] text-ink-400">{label}</p>
      <p className="figure mt-1 text-[22px] leading-none font-medium text-ink-900">{value}</p>
      {hint ? <p className="mt-1 text-[10px] text-ink-400">{hint}</p> : null}
    </div>
  );
}

export default async function PlatformOrganizationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · tenant detail"
      title="Inspect one organisation."
      description="Operational metadata, lifecycle state and administrative history. The tenant's materials, proposals, transactions and documents remain inside the tenant and are never readable from here."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.organizationsView)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="Tenant detail needs platform.organizations.view"
          capability="platform.organizations.view"
          description="Your account is a platform operator without this capability, so no tenant metadata is fetched."
        />
      </>
    );
  }

  const { id } = await params;
  const response = await apiGet<PlatformOrganizationDetail>(`/platform/organizations/${id}`);

  if (!response.ok) {
    return (
      <>
        {header}
        <Panel className="p-5 sm:p-6">
          <p className="label-mono text-[9px] text-ink-400">Organisation unavailable</p>
          <h2 className="mt-1.5 text-[15px] font-semibold text-ink-900">
            {response.status === 404 ? "No organisation with that identifier" : "Tenant detail could not be read"}
          </h2>
          <p className="mt-1.5 max-w-xl text-[12.5px] leading-relaxed text-ink-500">
            {response.status === 404
              ? "The identifier does not name a tenant. Nothing is shown rather than a partial or invented record."
              : response.error}
          </p>
          <Link
            href="/platform/organizations"
            className="mt-4 inline-flex h-9 items-center rounded-lg border border-paper-300 px-3.5 text-[12px] text-ink-600 hover:bg-paper-100"
          >
            ← Organisation register
          </Link>
        </Panel>
      </>
    );
  }

  const organisation = response.data;
  const canManage =
    canPlatform(user, PLATFORM_PERMISSION.organizationsManage) &&
    canPlatform(user, PLATFORM_PERMISSION.approvalsRequest);

  return (
    <>
      <div className="mb-4">
        <Link
          href="/platform/organizations"
          className="text-[11.5px] font-medium text-forest-700 hover:underline"
        >
          ← Organisation register
        </Link>
      </div>

      <Panel className="mb-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="label-mono text-[9px] text-forest-600">Inspecting organisation</p>
            <h1 className="mt-1 truncate text-[22px] leading-tight font-semibold tracking-[-0.02em] text-ink-900">
              {organisation.name}
            </h1>
            <p className="mt-1 truncate font-mono text-[10px] text-ink-400">
              {organisation.slug} · {organisation.id}
            </p>
            <p className="mt-1 text-[11px] text-ink-500">
              {sectorLabel(organisation.sector)} · {organisation.city ? `${organisation.city}, ` : ""}
              {organisation.country}
              {organisation.is_demo ? " · demo tenant" : ""}
            </p>
          </div>
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <OrganizationStatus organization={organisation} canManage={canManage} />
            {organisation.suspended_at ? (
              <p className="font-mono text-[9.5px] text-clay-500">
                suspended {formatDate(organisation.suspended_at)}
              </p>
            ) : null}
            <Link
              href={`/platform/approvals?organization_id=${organisation.id}`}
              className="text-[10.5px] text-forest-700 hover:underline"
            >
              Approval requests for this tenant →
            </Link>
          </div>
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            eyebrow="Memberships"
            title="Roster shape"
            subtitle="Counts by membership state. No names, emails or roles of individual members are exposed here."
          />
          <div className="grid grid-cols-2 gap-4 px-4 py-4 sm:grid-cols-4 sm:px-6">
            <Count label="Active" value={organisation.members.active} />
            <Count label="Deactivated" value={organisation.members.suspended} />
            <Count label="Invited" value={organisation.members.invited} />
            <Count label="Removed" value={organisation.members.removed} />
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-paper-200 px-4 py-4 sm:grid-cols-4 sm:px-6">
            <Count
              label="Invitations"
              value={organisation.invitations.pending}
              hint="pending, unexpired"
            />
            <Count label="Expired" value={organisation.invitations.expired} />
            <Count label="Accepted" value={organisation.invitations.accepted} />
            <Count label="Revoked" value={organisation.invitations.revoked} />
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Operational health"
            title="What the platform can verify"
            subtitle="Three checks computed from records: tenant state, membership presence and an active administrator. This is not a claim of application health."
            action={
              <Badge tone={healthStateTone(organisation.state)}>
                {healthStateLabel(organisation.state)}
              </Badge>
            }
          />
          <div className="space-y-3 px-4 py-4 sm:px-6">
            <div className="grid grid-cols-2 gap-4">
              <Count label="Active administrators" value={organisation.administrators.active ?? 0} />
              <div>
                <p className="label-mono text-[8.5px] text-ink-400">Last activity</p>
                <p className="mt-1 text-[13px] font-medium text-ink-900">
                  {relativeTime(organisation.last_activity_at)}
                </p>
                <p className="mt-1 text-[10px] text-ink-400">
                  {formatDate(organisation.last_activity_at)}
                </p>
              </div>
            </div>
            <ul className="flex flex-wrap gap-1.5">
              {organisation.checks.map((check) => (
                <li key={check}>
                  <Badge tone="outline" mono>
                    {check}
                  </Badge>
                </li>
              ))}
            </ul>
            {organisation.warnings.length === 0 ? (
              <p className="text-[11.5px] text-ink-500">
                No consistency warning is present for the checks above.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {organisation.warnings.map((warning) => (
                  <li key={warning} className="flex items-start gap-2 text-[11.5px] text-ink-600">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-clay-500" />
                    <span>
                      <span className="font-mono text-[9.5px] text-ink-400">{warning}</span>{" "}
                      {healthWarningCopy(warning)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <PanelHeader
            eyebrow="Audit"
            title="Recent privileged events"
            subtitle="Administrative changes and warning-or-higher events recorded against this tenant."
            action={
              <Link
                href={`/platform/audit?organization_id=${organisation.id}`}
                className="text-[11px] font-medium text-forest-700 hover:underline"
              >
                Filter journal →
              </Link>
            }
          />
          {organisation.recent_events.length === 0 ? (
            <EmptyState
              title="No privileged events"
              description="Nothing administrative or warning-or-higher has been recorded for this tenant."
            />
          ) : (
            <ul role="list" className="divide-y divide-paper-200">
              {organisation.recent_events.map((event) => (
                <li key={event.id} className="px-4 py-3 sm:px-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      tone={
                        event.severity === "critical"
                          ? "danger"
                          : event.severity === "warning"
                            ? "warning"
                            : "outline"
                      }
                      mono
                    >
                      {event.event_type}
                    </Badge>
                    <span className="ml-auto font-mono text-[9.5px] text-ink-300">
                      {relativeTime(event.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-ink-700">{event.summary}</p>
                  <p className="mt-0.5 font-mono text-[9px] text-ink-300">
                    {event.actor} · {formatDate(event.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Metadata"
            title="Record facts"
            subtitle="Safe operational fields only."
          />
          <dl className="space-y-2.5 px-4 py-4 text-[11.5px] sm:px-6">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-400">Created</dt>
              <dd className="text-ink-700">{formatDate(organisation.created_at)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-400">Suspended</dt>
              <dd className="text-ink-700">
                {organisation.suspended_at ? formatDate(organisation.suspended_at) : "—"}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-400">Sector</dt>
              <dd className="text-ink-700">{sectorLabel(organisation.sector)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-400">Location</dt>
              <dd className="text-right text-ink-700">
                {[organisation.city, organisation.country].filter(Boolean).join(", ")}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-400">Demo tenant</dt>
              <dd className="text-ink-700">{organisation.is_demo ? "Yes" : "No"}</dd>
            </div>
          </dl>
        </Panel>
      </div>

      <Panel className="mt-4">
        <PanelHeader
          eyebrow="Suspension semantics"
          title="What suspension does, exactly"
                      subtitle="These rules are enforced by the API on every request. The lifecycle buttons create an approval request; a different operator must approve it before it can execute."
        />
        <ul className="space-y-1.5 px-4 py-4 sm:px-6">
          {SUSPENSION_EFFECTS.map((effect) => (
            <li key={effect} className="flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-600">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-forest-600" />
              <span>{effect}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
