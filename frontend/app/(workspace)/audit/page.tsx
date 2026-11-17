import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { ActorSwitcher } from "@/components/workflow/actor-switcher";
import { apiGet } from "@/lib/api";
import { formatDate, relativeTime, titleCase } from "@/lib/format";
import type { Page } from "@/lib/types";
import type { AuditRecord } from "@/lib/workflow-types";

export const dynamic = "force-dynamic";

const ENTITY_FILTERS = [
  { key: "", label: "All entities" },
  { key: "proposal", label: "Proposals" },
  { key: "transaction", label: "Transactions" },
];

const SEVERITY_FILTERS = [
  { key: "", label: "All severities" },
  { key: "info", label: "Info" },
  { key: "warning", label: "Warnings" },
];

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const entityType = typeof params.entity_type === "string" ? params.entity_type : "";
  const severity = typeof params.severity === "string" ? params.severity : "";

  const query = new URLSearchParams({ page_size: "100" });
  if (entityType) query.set("entity_type", entityType);
  if (severity) query.set("severity", severity);

  const response = await apiGet<Page<AuditRecord>>(`/audit?${query.toString()}`);

  // A 403 is an authorization outcome, not an outage: it must never show API
  // startup or seeding instructions, and the filters would only repeat the 403.
  const accessDenied =
    !response.ok && (response.status === 403 || response.code === "forbidden");

  function href(next: { entity_type?: string; severity?: string }) {
    const nextQuery = new URLSearchParams();
    const entity = next.entity_type ?? entityType;
    const level = next.severity ?? severity;
    if (entity) nextQuery.set("entity_type", entity);
    if (level) nextQuery.set("severity", level);
    const suffix = nextQuery.toString();
    return suffix ? `/audit?${suffix}` : "/audit";
  }

  return (
    <>
      <PageHeader
        cinematic
        eyebrow="Audit journal · immutable record"
        title="Every decision leaves a trace."
        description="State changes, approvals, verifications and denied attempts are written inside the same database transaction as the operation they describe. Records are append-only; there is no endpoint that edits or deletes them."
        actions={<ActorSwitcher />}
      />

      {!accessDenied ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
        {ENTITY_FILTERS.map((item) => (
          <Link
            key={item.key || "all"}
            href={href({ entity_type: item.key })}
            className={[
              "rounded-xl border px-3 py-1.5 font-mono text-[10px] tracking-wide uppercase transition-premium",
              entityType === item.key
                ? "border-forest-700/30 bg-forest-900 text-paper-50 shadow-[0_8px_18px_-14px_rgba(16,41,26,0.7)]"
                : "border-paper-300/70 bg-paper-50/90 text-ink-500 hover:bg-paper-100 hover:text-ink-700",
            ].join(" ")}
          >
            {item.label}
          </Link>
        ))}
        <span className="mx-1 h-4 w-px bg-paper-300" />
        {SEVERITY_FILTERS.map((item) => (
          <Link
            key={item.key || "all"}
            href={href({ severity: item.key })}
            className={[
              "rounded-xl border px-3 py-1.5 font-mono text-[10px] tracking-wide uppercase transition-premium",
              severity === item.key
                ? "border-forest-700/30 bg-forest-900 text-paper-50 shadow-[0_8px_18px_-14px_rgba(16,41,26,0.7)]"
                : "border-paper-300/70 bg-paper-50/90 text-ink-500 hover:bg-paper-100 hover:text-ink-700",
            ].join(" ")}
          >
            {item.label}
          </Link>
        ))}
        </div>
      ) : null}

      {response.ok ? (
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-paper-200/80 px-5 py-4">
            <div>
              <p className="label-mono text-[8.5px] text-ink-400">Audit journal</p>
              <h2 className="text-[15px] font-semibold text-ink-900">{response.data.total} recorded events</h2>
            </div>
            <Badge tone="muted" mono>newest first</Badge>
          </div>

          {response.data.items.length === 0 ? (
            <EmptyState
              title="No audit events"
              description="Events appear as soon as a proposal, transaction or authorization attempt is recorded."
            />
          ) : (
            <ol className="divide-y divide-paper-200/80">
              {response.data.items.map((event) => {
                const entityHref =
                  event.entity_type === "proposal" && event.entity_id
                    ? `/proposals/${event.entity_id}`
                    : event.entity_type === "transaction" && event.entity_id
                      ? `/transactions/${event.entity_id}`
                      : null;
                return (
                  <li key={event.id} className="px-5 py-3.5 transition-premium hover:bg-paper-100/40">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={event.severity === "warning" ? "warning" : "outline"} mono>
                        {event.event_type}
                      </Badge>
                      <span className="font-mono text-[9px] tracking-wide text-ink-400 uppercase">
                        {event.entity_type}
                        {entityHref ? (
                          <Link href={entityHref} className="ml-1 text-forest-700 hover:underline">
                            {event.entity_id?.slice(0, 8)}
                          </Link>
                        ) : event.entity_id ? (
                          ` ${event.entity_id.slice(0, 8)}`
                        ) : null}
                      </span>
                      <span className="font-mono text-[9px] text-ink-300">
                        {event.previous_state ? titleCase(event.previous_state) : "—"} → {event.new_state ? titleCase(event.new_state) : "—"}
                      </span>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-relaxed text-ink-700">{event.summary}</p>
                    {event.reason ? <p className="mt-1 text-[11px] leading-relaxed text-ink-500">Reason: {event.reason}</p> : null}
                    <p className="mt-1 font-mono text-[9px] text-ink-300">
                      {event.actor_id ?? event.actor} · {formatDate(event.created_at)} · {relativeTime(event.created_at)}
                    </p>
                  </li>
                );
              })}
            </ol>
          )}
        </Panel>
      ) : accessDenied ? (
        <DataUnavailable
          title="Audit journal access denied"
          message="Your role does not include audit-journal visibility, so no events are shown. The API enforced the same rule, so this page never receives records you are not authorised to read."
          hint="Ask an organisation administrator to grant audit visibility if your responsibilities require it."
          troubleshooting={false}
        />
      ) : (
        <DataUnavailable message={response.error} title="Audit journal unavailable" />
      )}

      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        Organization-scoped actors only see events recorded against their own organisation. Platform-wide visibility requires admin, reviewer, approver, auditor or observer authority.
      </p>
    </>
  );
}
