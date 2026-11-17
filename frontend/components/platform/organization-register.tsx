import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { formatDate, sectorLabel } from "@/lib/format";
import {
  platformHref,
  platformStatusLabel,
  platformStatusTone,
} from "@/lib/platform";
import type { PlatformOrganizationRow } from "@/lib/platform-types";

export type RegisterFilters = { q: string; status: string };

/**
 * Platform-only tenant register. Rows carry only safe operational fields; the
 * detail link is the only way to see more, and the API scopes that request to
 * platform operators.
 */
export function OrganizationRegister({
  items,
  total,
  page,
  pageSize,
  hasMore,
  filters,
}: {
  items: PlatformOrganizationRow[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
  filters: RegisterFilters;
}) {
  const previousHref = platformHref("/platform/organizations", {
    q: filters.q,
    status: filters.status,
    page: page - 1,
  });
  const nextHref = platformHref("/platform/organizations", {
    q: filters.q,
    status: filters.status,
    page: page + 1,
  });

  return (
    <div>
      <ul role="list" className="divide-y divide-paper-200">
        {items.map((organisation) => (
          <li key={organisation.id} className="px-4 py-3.5 sm:px-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <Link
                  href={`/platform/organizations/${organisation.id}`}
                  className="block truncate text-[13.5px] font-medium text-ink-900 hover:text-forest-700"
                >
                  {organisation.name}
                </Link>
                <p className="mt-0.5 truncate font-mono text-[10px] text-ink-400">
                  {organisation.slug} · {sectorLabel(organisation.sector)} · {organisation.country}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <Badge tone={platformStatusTone(organisation.status)} mono>
                  {platformStatusLabel(organisation.status)}
                </Badge>
                <span className="font-mono text-[10px] text-ink-500">
                  {`${organisation.active_members} active${
                    organisation.suspended_members > 0
                      ? ` · ${organisation.suspended_members} deactivated`
                      : ""
                  }`}
                </span>
                <span className="font-mono text-[10px] text-ink-400">
                  {`${organisation.pending_invitations} pending invite${
                    organisation.pending_invitations === 1 ? "" : "s"
                  }`}
                </span>
                <span className="text-[10.5px] whitespace-nowrap text-ink-400">
                  created {formatDate(organisation.created_at)}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-paper-200 px-4 py-3 sm:px-6">
        <p className="font-mono text-[10px] text-ink-400">
          page {page} · {total} organisation{total === 1 ? "" : "s"} · {pageSize} per page
        </p>
        <div className="flex items-center gap-2">
          {page > 1 ? (
            <Link
              href={previousHref}
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
              href={nextHref}
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
