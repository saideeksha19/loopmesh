import { EmptyState } from "@/components/ui/empty-state";
import type { AuditEvent } from "@/lib/types";
import { relativeTime } from "@/lib/format";

const EVENT_LABEL: Record<string, string> = {
  "material.created": "Material registered",
  "material.registered": "Material registered",
  "materials.imported": "CSV imported",
  "discovery.run": "Discovery run",
  "proposal.submitted": "Proposal submitted",
  "transaction.verified": "Transaction verified",
  "seed.demo_loaded": "Demo dataset loaded",
};

export function ActivityFeed({ events }: { events: AuditEvent[] }) {
  if (!events.length) {
    return (
      <EmptyState
        title="No activity recorded yet"
        description="Register a material stream or run discovery to populate the audit journal."
      />
    );
  }

  return (
    <ul className="divide-y divide-paper-200/80">
      {events.map((event, idx) => (
        <li
          key={event.id}
          className="flex gap-3 px-5 py-3 transition-premium hover:bg-paper-100/50 sm:px-6 animate-rise"
          style={{ animationDelay: `${idx * 25}ms` }}
        >
          <span className="relative mt-1.5 flex h-2.5 w-2.5 shrink-0 items-center justify-center">
            <span
              className={[
                "h-1.5 w-1.5 rounded-full",
                event.severity === "warning"
                  ? "bg-clay-500"
                  : event.severity === "critical"
                    ? "bg-rust-500"
                    : "bg-lime-500 shadow-[0_0_8px_rgba(198,243,92,0.45)]",
              ].join(" ")}
            />
          </span>
          <div className="min-w-0">
            <p className="text-[12px] leading-snug text-ink-700">{event.summary}</p>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-mono text-[9.5px] tracking-wide text-ink-400">
              <span className="uppercase">{EVENT_LABEL[event.event_type] ?? event.event_type}</span>
              <span aria-hidden>·</span>
              <span>{event.actor}</span>
              <span aria-hidden>·</span>
              <span>{relativeTime(event.created_at)}</span>
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
