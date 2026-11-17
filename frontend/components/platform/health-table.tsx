import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { formatDate, relativeTime } from "@/lib/format";
import {
  healthStateLabel,
  healthStateTone,
  healthWarningCopy,
  platformHref,
  platformStatusLabel,
  platformStatusTone,
} from "@/lib/platform";
import type { PlatformTenantHealth } from "@/lib/platform-types";

/**
 * Bounded operational health view. Each row states exactly which signals were
 * checked, so "operational" can never be read as a claim of application health.
 */
export function HealthTable({
  items,
  total,
  page,
  pageSize,
  hasMore,
}: {
  items: PlatformTenantHealth[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}) {
  return (
    <div>
      <ul role="list" className="divide-y divide-paper-200">
        {items.map((tenant) => {
          const organisation = tenant.organization;
          return (
            <li key={organisation.id} className="px-4 py-4 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link
                    href={`/platform/organizations/${organisation.id}`}
                    className="block truncate text-[13.5px] font-medium text-ink-900 hover:text-forest-700"
                  >
                    {organisation.name}
                  </Link>
                  <p className="truncate font-mono text-[10px] text-ink-400">
                    {organisation.slug} · last activity {relativeTime(tenant.last_activity_at)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={platformStatusTone(organisation.status)} mono>
                    {platformStatusLabel(organisation.status)}
                  </Badge>
                  <Badge tone={healthStateTone(tenant.state)}>
                    {healthStateLabel(tenant.state)}
                  </Badge>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-[10px] text-ink-500 sm:grid-cols-3 lg:grid-cols-6">
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Active members
                  </span>
                  {tenant.active_members}
                </span>
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Administrators
                  </span>
                  {tenant.active_administrators}
                </span>
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Pending invites
                  </span>
                  {tenant.pending_invitations}
                </span>
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Admin changes
                  </span>
                  {tenant.admin_changes_window}
                </span>
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Security events
                  </span>
                  {tenant.security_events_window}
                </span>
                <span>
                  <span className="block text-[9px] tracking-wide text-ink-400 uppercase">
                    Auth failures
                  </span>
                  {tenant.member_auth_failures_window}
                </span>
              </div>

              {tenant.warnings.length > 0 ? (
                <ul className="mt-3 space-y-1">
                  {tenant.warnings.map((warning) => (
                    <li key={warning} className="flex items-start gap-1.5 text-[11px] text-ink-600">
                      <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-clay-500" />
                      <span>
                        <span className="font-mono text-[9.5px] text-ink-400">{warning}</span>{" "}
                        {healthWarningCopy(warning)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

              <p className="mt-2 text-[10px] text-ink-400">
                Checks: {tenant.checks.join(" · ")} · last activity{" "}
                {formatDate(tenant.last_activity_at)}
              </p>
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-paper-200 px-4 py-3 sm:px-6">
        <p className="font-mono text-[10px] text-ink-400">
          page {page} · {total} tenant{total === 1 ? "" : "s"} · {pageSize} per page
        </p>
        <div className="flex items-center gap-2">
          {page > 1 ? (
            <Link
              href={platformHref("/platform/health", { page: page - 1 })}
              className="rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 text-[11px] text-ink-600 hover:bg-paper-100"
            >
              ← Previous
            </Link>
          ) : (
            <span className="rounded-lg border border-paper-200 px-2.5 py-1.5 text-[11px] text-ink-300">
              ← Previous
            </span>
          )}
          {hasMore ? (
            <Link
              href={platformHref("/platform/health", { page: page + 1 })}
              className="rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 text-[11px] text-ink-600 hover:bg-paper-100"
            >
              Next →
            </Link>
          ) : (
            <span className="rounded-lg border border-paper-200 px-2.5 py-1.5 text-[11px] text-ink-300">
              Next →
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
