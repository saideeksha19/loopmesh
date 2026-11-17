"use client";

import { useState } from "react";

import { authFetch } from "@/lib/client-auth";
import {
  AUDIT_EXPORT_MAX_DAYS,
  AUDIT_EXPORT_MAX_ROWS,
  platformQuery,
} from "@/lib/platform";
import type { AuditFilterValues } from "@/components/platform/audit-filters";

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return Number.NaN;
  return Math.floor((end - start) / 86_400_000) + 1;
}

/**
 * Downloads through the authenticated proxy. The API applies the same filters
 * and redaction as the journal, refuses an unbounded range or row count, and
 * writes its own `platform.audit.exported` event before returning the file.
 */
export function AuditExport({
  values,
  canExport,
}: {
  values: AuditFilterValues;
  canExport: boolean;
}) {
  const today = new Date();
  const weekAgo = new Date(today.getTime() - 6 * 86_400_000);
  const [from, setFrom] = useState(values.created_from || isoDate(weekAgo));
  const [to, setTo] = useState(values.created_to || isoDate(today));
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const span = daysBetween(from, to);
  const tooLong = Number.isFinite(span) && span > AUDIT_EXPORT_MAX_DAYS;
  const inverted = Number.isFinite(span) && span <= 0;
  const blocked = !from || !to || tooLong || inverted;

  async function download() {
    if (!canExport || blocked || pending) return;
    setPending(true);
    setError(null);
    setMessage(null);
    const query = platformQuery({
      created_from: `${from}T00:00:00`,
      created_to: `${to}T23:59:59.999999`,
      format,
      actor: values.actor,
      event_type: values.event_type,
      entity_type: values.entity_type,
      entity_id: values.entity_id,
      target_user_id: values.target_user_id,
      organization_id: values.organization_id,
    });
    try {
      const response = await authFetch(`/platform/audit/export?${query.toString()}`);
      if (!response.ok) {
        let detail = `The API rejected the export (${response.status}).`;
        try {
          const body = (await response.json()) as {
            error?: { message?: string; details?: { reason?: string; max_rows?: number } };
          };
          if (body.error?.message) detail = body.error.message;
          if (body.error?.details?.reason === "export_too_large") {
            detail += ` Narrow the filters to ${body.error.details.max_rows ?? AUDIT_EXPORT_MAX_ROWS} rows or fewer.`;
          }
        } catch {
          /* non-JSON refusal */
        }
        setError(detail);
        return;
      }
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") ?? "";
      const match = /filename="([A-Za-z0-9._-]+)"/.exec(disposition);
      const filename = match?.[1] ?? `loopmesh-audit.${format}`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage(`Export requested; ${filename} was downloaded and the export was audited.`);
    } catch {
      setError("The API is not reachable. No file was generated.");
    } finally {
      setPending(false);
    }
  }

  if (!canExport) {
    return (
      <p className="text-[11.5px] leading-relaxed text-ink-500">
        Export needs <code className="font-mono text-[10px]">platform.audit.export</code> in
        addition to <code className="font-mono text-[10px]">platform.audit.view</code>. Reading the
        journal does not grant the ability to take a copy.
      </p>
    );
  }

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">From (UTC, required)</span>
          <input
            type="date"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
            className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">To (UTC, required)</span>
          <input
            type="date"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
          />
        </label>
        <label className="block">
          <span className="label-mono text-[8.5px] text-ink-400">Format</span>
          <select
            value={format}
            onChange={(event) => setFormat(event.target.value as "csv" | "json")}
            className="mt-1 h-9 w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 text-[12px] text-ink-800 outline-none focus:border-forest-600"
          >
            <option value="csv">CSV (spreadsheet-safe)</option>
            <option value="json">JSON</option>
          </select>
        </label>
      </div>

      <p className="mt-2 text-[10.5px] leading-relaxed text-ink-400">
        Both dates are required. The API accepts at most {AUDIT_EXPORT_MAX_DAYS} days and{" "}
        {AUDIT_EXPORT_MAX_ROWS.toLocaleString()} rows, uses the journal&apos;s current filters and
        redaction, orders deterministically oldest-first, and records who exported what. Neither
        format can modify or delete the source records.
      </p>

      {tooLong ? (
        <p role="alert" className="mt-2 text-[11px] text-rust-500">
          This range is {span} days. Narrow it to {AUDIT_EXPORT_MAX_DAYS} days or fewer.
        </p>
      ) : null}
      {inverted ? (
        <p role="alert" className="mt-2 text-[11px] text-rust-500">
          The start date must not be after the end date.
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={download}
          disabled={pending || blocked}
          className="h-9 rounded-lg bg-forest-900 px-3.5 text-[12px] font-medium text-lime-300 hover:bg-forest-800 disabled:opacity-50"
        >
          {pending ? "Preparing export…" : `Export ${format.toUpperCase()}`}
        </button>
        <span className="text-[10px] text-ink-400">
          Active journal filters are included in the export.
        </span>
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-[11.5px] text-rust-500">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="mt-2 text-[11.5px] text-forest-700">
          {message}
        </p>
      ) : null}
    </div>
  );
}
