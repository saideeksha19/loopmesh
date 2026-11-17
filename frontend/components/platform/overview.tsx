import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { StatCard } from "@/components/ui/stat-card";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import {
  platformStatusLabel,
  platformStatusTone,
} from "@/lib/platform";
import type { PlatformDashboard } from "@/lib/platform-types";

/**
 * Aggregate estate view. Every number comes from the API's grouped queries;
 * nothing here is a browser-side estimate or a demonstration figure.
 */
export function PlatformOverview({ data }: { data: PlatformDashboard }) {
  const { organisations, users, memberships } = data;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Organisations"
          value={String(organisations.total)}
          meta={`${organisations.active} active · ${organisations.suspended} suspended · ${organisations.created_in_window} created in the last ${data.window_days} days`}
          accent
        />
        <StatCard
          label="User accounts"
          value={String(users.total)}
          meta={`${users.active} active accounts across the whole platform`}
        />
        <StatCard
          label="Active memberships"
          value={String(memberships.active)}
          meta={`${memberships.invited} invited · ${memberships.suspended} deactivated · ${memberships.removed} removed`}
        />
        <StatCard
          label="Pending invitations"
          value={String(data.pending_invitations)}
          meta={`${data.failed_logins_window} failed sign-in${
            data.failed_logins_window === 1 ? "" : "s"
          } in the last ${data.failure_window_hours} hours`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            eyebrow="Individual records"
            title="Recently created organisations"
            subtitle={`The newest ${data.recent_organisations.length} organisation record${
              data.recent_organisations.length === 1 ? "" : "s"
            }, named because operators need to act on them. Names, slugs and lifecycle state only.`}
          />
          {data.recent_organisations.length === 0 ? (
            <EmptyState
              title="No organisations yet"
              description="Organisation records appear here as soon as the first tenant is created."
            />
          ) : (
            <ul role="list" className="divide-y divide-paper-200">
              {data.recent_organisations.map((organisation) => (
                <li key={organisation.id} className="px-5 py-3 sm:px-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <Link
                        href={`/platform/organizations/${organisation.id}`}
                        className="block truncate text-[13px] font-medium text-ink-900 hover:text-forest-700"
                      >
                        {organisation.name}
                      </Link>
                      <p className="truncate font-mono text-[10px] text-ink-400">
                        {organisation.slug} · {titleCase(organisation.sector)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={platformStatusTone(organisation.status)} mono>
                        {platformStatusLabel(organisation.status)}
                      </Badge>
                      <span className="text-[10.5px] text-ink-400">
                        {formatDate(organisation.created_at)}
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Security & administration"
            title="Recent privileged events"
            subtitle={`Administrative changes, security-sensitive account actions and warning-or-higher events from the last ${data.window_days} days. Payloads are not shown here.`}
          />
          {data.recent_events.length === 0 ? (
            <EmptyState
              title="No privileged events in this window"
              description="Nothing was recorded in the selected window; an empty list is an honest zero, not a missing feed."
            />
          ) : (
            <ul role="list" className="divide-y divide-paper-200">
              {data.recent_events.map((event) => (
                <li key={event.id} className="px-5 py-3 sm:px-6">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={event.severity === "critical" ? "danger" : event.severity === "warning" ? "warning" : "outline"} mono>
                      {event.event_type}
                    </Badge>
                    {event.organization_name ? (
                      <span className="truncate text-[10.5px] text-ink-500">
                        {event.organization_name}
                      </span>
                    ) : null}
                    <span className="ml-auto font-mono text-[9.5px] text-ink-300">
                      {relativeTime(event.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-ink-700">{event.summary}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="border-t border-paper-200 px-5 py-3 sm:px-6">
            <Link
              href="/platform/audit"
              className="text-[11.5px] font-medium text-forest-700 hover:underline"
            >
              Open the audit journal →
            </Link>
          </div>
        </Panel>
      </div>
    </div>
  );
}
