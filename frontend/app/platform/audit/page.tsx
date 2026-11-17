import type { Metadata } from "next";

import { AuditExport } from "@/components/platform/audit-export";
import { AuditFilters, type AuditFilterValues } from "@/components/platform/audit-filters";
import { AuditLog } from "@/components/platform/audit-log";
import { PlatformDenied } from "@/components/platform/platform-denied";
import { Badge } from "@/components/ui/badge";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import {
  AUDIT_ORDER_NOTE,
  PLATFORM_PERMISSION,
  canPlatform,
  platformHref,
  readParam,
} from "@/lib/platform";
import type {
  PlatformAuditEvent,
  PlatformOrganizationRow,
} from "@/lib/platform-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Platform audit journal",
  description: "Search the append-only platform-wide audit journal.",
  robots: { index: false, follow: false },
};

const PAGE_SIZE = 25;

export default async function PlatformAuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const header = (
    <PageHeader
      eyebrow="Platform · audit"
      title="Every privileged action, one journal."
      description="Search existing audit records across tenants by date, actor, organisation, event, entity or target account. Records are append-only: the console offers no way to edit or delete history."
    />
  );

  if (!canPlatform(user, PLATFORM_PERMISSION.audit)) {
    return (
      <>
        {header}
        <PlatformDenied
          title="The platform journal needs platform.audit.view"
          capability="platform.audit.view"
          description="Your account is a platform operator without this capability. Organisation-level audit stays tenant-scoped and is not a substitute for this view."
        />
      </>
    );
  }

  const params = await searchParams;
  const values: AuditFilterValues = {
    created_from: readParam(params, "created_from").slice(0, 10),
    created_to: readParam(params, "created_to").slice(0, 10),
    actor: readParam(params, "actor").slice(0, 120),
    event_type: readParam(params, "event_type").slice(0, 64),
    entity_type: readParam(params, "entity_type").slice(0, 64),
    entity_id: readParam(params, "entity_id").slice(0, 36),
    target_user_id: readParam(params, "target_user_id").slice(0, 36),
    organization_id: readParam(params, "organization_id").slice(0, 36),
  };
  const pageParam = Number.parseInt(readParam(params, "page") || "1", 10);
  const page = Number.isFinite(pageParam) && pageParam > 0 ? pageParam : 1;

  const query = {
    created_from: values.created_from ? `${values.created_from}T00:00:00` : "",
    created_to: values.created_to ? `${values.created_to}T23:59:59` : "",
    actor: values.actor,
    event_type: values.event_type,
    entity_type: values.entity_type,
    entity_id: values.entity_id,
    target_user_id: values.target_user_id,
    organization_id: values.organization_id,
    page,
    page_size: PAGE_SIZE,
  };

  const [response, organisationResponse] = await Promise.all([
    apiGet<Page<PlatformAuditEvent>>(platformHref("/platform/audit", query)),
    apiGet<Page<PlatformOrganizationRow>>("/platform/organizations?page_size=200"),
  ]);

  const organisations = organisationResponse.ok ? organisationResponse.data.items : [];
  const filtered = Object.entries(values).some(([, value]) => value.length > 0);

  return (
    <>
      {header}

      <Panel>
        <PanelHeader
          eyebrow="Search"
          title="Filter the journal"
          subtitle="Actor matches a substring of the recorded email or label; ids must be exact. Page size is fixed and bounded by the API."
          action={
            <Badge tone="muted" mono>
              {AUDIT_ORDER_NOTE}
            </Badge>
          }
        />
        <AuditFilters values={values} organizations={organisations} />

        {!response.ok ? (
          <div className="px-4 py-4 sm:px-6">
            <DataUnavailable
              title="Platform journal unavailable"
              message={response.error}
              hint="Invalid filter values are rejected by the API rather than silently ignored."
            />
          </div>
        ) : response.data.items.length === 0 ? (
          <EmptyState
            title={filtered ? "No events match these filters" : "No audit events yet"}
            description={
              filtered
                ? "No recorded event matches this combination. Widen the date range or remove a filter."
                : "Events appear as soon as an administrative or security-sensitive action is recorded."
            }
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-paper-200 px-4 py-3 sm:px-6">
              <p className="text-[12px] font-medium text-ink-800">
                {response.data.total} recorded event{response.data.total === 1 ? "" : "s"}
              </p>
              <p className="font-mono text-[10px] text-ink-400">
                page {response.data.page} · {response.data.page_size} per page
              </p>
            </div>
            <AuditLog items={response.data.items} />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-paper-200 px-4 py-3 sm:px-6">
              <p className="font-mono text-[10px] text-ink-400">{AUDIT_ORDER_NOTE}</p>
              <div className="flex items-center gap-2">
                <a
                  href={platformHref("/platform/audit", { ...values, page: page - 1 })}
                  aria-disabled={page <= 1}
                  className={[
                    "rounded-lg border px-2.5 py-1.5 text-[11px]",
                    page <= 1
                      ? "pointer-events-none border-paper-200 text-ink-300"
                      : "border-paper-300 bg-paper-50 text-ink-600 hover:bg-paper-100",
                  ].join(" ")}
                >
                  ← Previous
                </a>
                <a
                  href={platformHref("/platform/audit", { ...values, page: page + 1 })}
                  aria-disabled={!response.data.has_more}
                  className={[
                    "rounded-lg border px-2.5 py-1.5 text-[11px]",
                    !response.data.has_more
                      ? "pointer-events-none border-paper-200 text-ink-300"
                      : "border-paper-300 bg-paper-50 text-ink-600 hover:bg-paper-100",
                  ].join(" ")}
                >
                  Next →
                </a>
              </div>
            </div>
          </>
        )}
      </Panel>

      <Panel className="mt-4">
        <PanelHeader
          eyebrow="Export"
          title="Take a bounded copy"
          subtitle="The export is a separate capability from reading. It applies these filters and the same redaction, and is itself audited."
        />
        <div className="px-4 py-4 sm:px-6">
          <AuditExport
            values={values}
            canExport={canPlatform(user, PLATFORM_PERMISSION.auditExport)}
          />
        </div>
      </Panel>

      <p className="mt-4 text-[10.5px] leading-relaxed text-ink-400">
        Payloads are redacted at the serialisation boundary before they leave the API:
        authentication events keep only an allow-list of outcome fields, keys naming passwords,
        tokens, hashes, credentials, keys, cookies or sessions become <code>[redacted]</code>, long
        strings are truncated and the redacted field names are reported. The stored record is never
        changed by reading it.
      </p>
    </>
  );
}
