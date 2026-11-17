import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import type { AuditRecord } from "@/lib/workflow-types";

function entityHref(event: AuditRecord): string | null {
  if (!event.entity_id) return null;
  if (event.entity_type === "proposal") return `/proposals/${event.entity_id}`;
  if (event.entity_type === "transaction") return `/transactions/${event.entity_id}`;
  return null;
}

function metadataEntries(payload: Record<string, unknown>): [string, string][] {
  return Object.entries(payload ?? {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .filter(([key]) => !["demo"].includes(key))
    .map(([key, value]) => [
      key,
      typeof value === "object" ? JSON.stringify(value) : String(value),
    ]);
}

/**
 * Read-only audit timeline.
 *
 * Events are produced by the API and never edited here: there is no mutation
 * affordance on purpose. Optional metadata is rendered defensively so an older
 * event without reason/payload still renders.
 */
export function AuditTimeline({
  events,
  emptyTitle = "No audit events",
  emptyDescription = "Events appear as soon as a record is created, changed or denied.",
}: {
  events: AuditRecord[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (!events.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <ol className="divide-y divide-paper-200">
      {events.map((event) => {
        const href = entityHref(event);
        const metadata = metadataEntries(event.payload);
        return (
          <li key={event.id} className="px-4 py-3.5 sm:px-5">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone={event.severity === "warning" ? "warning" : "outline"} mono>
                {event.event_type}
              </Badge>
              <span className="font-mono text-[9px] tracking-wide text-ink-400 uppercase">
                {event.entity_type}
                {href && event.entity_id ? (
                  <Link href={href} className="ml-1 text-forest-700 hover:underline">
                    {event.entity_id.slice(0, 8)}
                  </Link>
                ) : event.entity_id ? (
                  ` ${event.entity_id.slice(0, 8)}`
                ) : null}
              </span>
              {event.previous_state || event.new_state ? (
                <span className="font-mono text-[9px] text-ink-300">
                  {event.previous_state ? titleCase(event.previous_state) : "—"} →{" "}
                  {event.new_state ? titleCase(event.new_state) : "—"}
                </span>
              ) : null}
            </div>

            <p className="mt-1 text-[11.5px] leading-relaxed text-ink-700">{event.summary}</p>

            {event.reason ? (
              <p className="mt-1 rounded-md border border-paper-200 bg-paper-50 px-2 py-1.5 text-[11px] leading-relaxed text-ink-500">
                {event.reason}
              </p>
            ) : null}

            {metadata.length ? (
              <dl className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                {metadata.map(([key, value]) => (
                  <div key={key} className="flex items-baseline gap-1.5">
                    <dt className="font-mono text-[8.5px] tracking-wide text-ink-300 uppercase">
                      {key}
                    </dt>
                    <dd className="max-w-[320px] truncate text-[10.5px] text-ink-500">{value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            <p className="mt-1 font-mono text-[9px] text-ink-300">
              {event.actor_id ?? event.actor} · {formatDate(event.created_at)} ·{" "}
              {relativeTime(event.created_at)}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
