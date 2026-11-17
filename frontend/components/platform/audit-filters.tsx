import Link from "next/link";

import type { PlatformOrganizationRow } from "@/lib/platform-types";

export type AuditFilterValues = {
  created_from: string;
  created_to: string;
  actor: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  target_user_id: string;
  organization_id: string;
};

const INPUT_CLASS =
  "mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600";

/**
 * Server-rendered GET form: filters are part of the URL, so a filtered journal
 * is linkable, refreshable and needs no client state. The API validates every
 * value again and bounds the page size.
 */
export function AuditFilters({
  values,
  organizations,
}: {
  values: AuditFilterValues;
  organizations: PlatformOrganizationRow[];
}) {
  return (
    <form
      method="get"
      action="/platform/audit"
      role="search"
      aria-label="Filter the platform audit journal"
      className="border-b border-paper-200 px-4 py-4 sm:px-6"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">From (UTC date)</span>
          <input
            type="date"
            name="created_from"
            defaultValue={values.created_from}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">To (UTC date)</span>
          <input
            type="date"
            name="created_to"
            defaultValue={values.created_to}
            className={INPUT_CLASS}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Organisation</span>
          <select
            name="organization_id"
            defaultValue={values.organization_id}
            className={INPUT_CLASS}
          >
            <option value="">All organisations</option>
            {organizations.map((organisation) => (
              <option key={organisation.id} value={organisation.id}>
                {organisation.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Event type</span>
          <input
            type="text"
            name="event_type"
            defaultValue={values.event_type}
            placeholder="membership.changed"
            className={`${INPUT_CLASS} font-mono`}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Actor (contains)</span>
          <input
            type="text"
            name="actor"
            defaultValue={values.actor}
            placeholder="email or label"
            className={INPUT_CLASS}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Entity type</span>
          <input
            type="text"
            name="entity_type"
            defaultValue={values.entity_type}
            placeholder="organization_membership"
            className={`${INPUT_CLASS} font-mono`}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Entity id</span>
          <input
            type="text"
            name="entity_id"
            defaultValue={values.entity_id}
            placeholder="UUID"
            className={`${INPUT_CLASS} font-mono`}
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Target user id</span>
          <input
            type="text"
            name="target_user_id"
            defaultValue={values.target_user_id}
            placeholder="UUID"
            className={`${INPUT_CLASS} font-mono`}
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="submit"
          className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 transition-colors hover:bg-forest-800"
        >
          Apply filters
        </button>
        <Link
          href="/platform/audit"
          className="h-9 rounded-lg border border-paper-300 px-3.5 pt-2 text-[12px] text-ink-600 hover:bg-paper-100"
        >
          Reset
        </Link>
        <p className="text-[10.5px] text-ink-400">
          Filters combine with AND. Dates are inclusive; invalid or inverted ranges are rejected by
          the API rather than silently widened.
        </p>
      </div>
    </form>
  );
}
