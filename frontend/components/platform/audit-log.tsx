import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import type { PlatformAuditEvent } from "@/lib/platform-types";

function severityTone(severity: string) {
  if (severity === "critical") return "danger" as const;
  if (severity === "warning") return "warning" as const;
  return "outline" as const;
}

/**
 * Platform-wide audit journal rows.
 *
 * Payloads arrive already redacted by the API: authentication payloads are cut
 * to an allow-list and secret-named keys are replaced before serialisation. The
 * journal is append-only, so nothing on this screen edits history.
 */
export function AuditLog({ items }: { items: PlatformAuditEvent[] }) {
  return (
    <ul role="list" className="divide-y divide-paper-200">
      {items.map((event) => (
        <li key={event.id} className="px-4 py-3.5 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={severityTone(event.severity)} mono>
              {event.event_type}
            </Badge>
            {event.organization_name ? (
              event.organization_id ? (
                <Link
                  href={`/platform/organizations/${event.organization_id}`}
                  className="truncate text-[11px] text-forest-700 hover:underline"
                >
                  {event.organization_name}
                </Link>
              ) : (
                <span className="truncate text-[11px] text-ink-500">{event.organization_name}</span>
              )
            ) : (
              <span className="font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">
                platform-wide
              </span>
            )}
            <span className="font-mono text-[9px] tracking-wide text-ink-400 uppercase">
              {event.entity_type}
              {event.entity_id ? ` ${event.entity_id.slice(0, 8)}` : ""}
            </span>
            <span className="font-mono text-[9px] text-ink-300">
              {event.previous_state ? titleCase(event.previous_state) : "—"} →{" "}
              {event.new_state ? titleCase(event.new_state) : "—"}
            </span>
            <span className="ml-auto font-mono text-[9.5px] whitespace-nowrap text-ink-300">
              {relativeTime(event.created_at)}
            </span>
          </div>

          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-700">{event.summary}</p>
          {event.reason ? (
            <p className="mt-1 text-[11px] leading-relaxed text-ink-500">Reason: {event.reason}</p>
          ) : null}

          <p className="mt-1 font-mono text-[9px] text-ink-300">
            {event.actor}
            {event.actor_id ? ` · actor ${event.actor_id.slice(0, 8)}` : ""} ·{" "}
            {formatDate(event.created_at)}
          </p>

          {event.redacted_fields.length > 0 ? (
            <p className="mt-1 font-mono text-[9px] text-clay-500">
              redacted: {event.redacted_fields.join(", ")}
            </p>
          ) : null}

          {Object.keys(event.payload).length > 0 ? (
            <details className="mt-1.5">
              <summary className="cursor-pointer font-mono text-[9.5px] text-ink-400 hover:text-ink-600">
                Event payload (redacted)
              </summary>
              <pre className="mt-1.5 overflow-x-auto rounded-lg border border-paper-200 bg-paper-50 p-2.5 font-mono text-[10px] leading-relaxed text-ink-600">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
