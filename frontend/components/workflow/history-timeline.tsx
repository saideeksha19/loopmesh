import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import type { Transition } from "@/lib/workflow-types";

export function TransitionTimeline({
  items,
  emptyNote,
}: {
  items: Transition[];
  emptyNote?: string;
}) {
  if (!items.length) {
    return (
      <EmptyState
        title="No recorded transitions"
        description={
          emptyNote ??
          "This record has no lifecycle history yet. Every future state change is recorded here with its actor and reason."
        }
      />
    );
  }

  return (
    <ol className="divide-y divide-paper-200">
      {items.map((transition) => (
        <li key={transition.id} className="flex gap-3 px-4 py-3.5 sm:px-5">
          <div className="mt-1 flex flex-col items-center">
            <span className="h-1.5 w-1.5 rounded-full bg-forest-600" />
            <span className="mt-1 w-px flex-1 bg-paper-200" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="forest" mono>
                {transition.action}
              </Badge>
              <span className="font-mono text-[10px] text-ink-400">
                {titleCase(transition.from_state)} → {titleCase(transition.to_state)}
              </span>
            </div>
            <p className="mt-1 text-[11.5px] text-ink-600">
              {transition.actor_id}
              <span className="ml-1.5 font-mono text-[9px] tracking-wide text-ink-300 uppercase">
                {transition.actor_role}
              </span>
            </p>
            {transition.reason ? (
              <p className="mt-1 rounded-md border border-paper-200 bg-paper-50 px-2 py-1.5 text-[11px] leading-relaxed text-ink-500">
                {transition.reason}
              </p>
            ) : null}
            <p className="mt-1 font-mono text-[9px] text-ink-300">
              {formatDate(transition.occurred_at)} · {relativeTime(transition.occurred_at)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
