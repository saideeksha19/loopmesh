"use client";

import { useState } from "react";

import { postFile } from "@/lib/client-api";
import type { CsvImportReport } from "@/lib/types";

const REQUIRED = [
  "organization_slug",
  "reference_code",
  "name",
  "category",
  "unit",
  "quantity_available",
];

const OPTIONAL = [
  "condition",
  "hazard_class",
  "description",
  "handling_requirements",
  "origin_process",
  "availability_start",
  "availability_end",
  "purity_pct",
  "moisture_pct",
  "contamination_pct",
  "ph_value",
  "particle_size_mm",
  "calorific_value_mj_kg",
  "assay_method",
];

export function CsvImport({
  onImported,
  onCancel,
}: {
  onImported: (report: CsvImportReport) => void;
  onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const result = await postFile<CsvImportReport>("/materials/import", file);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onImported(result.data);
  }

  return (
    <div>
      <label
        htmlFor="csv-file"
        className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-paper-300 bg-paper-50 px-4 py-8 text-center transition-colors hover:border-forest-600/40 hover:bg-paper-100"
      >
        <span className="label-mono text-[9px] text-ink-400">Structured data only</span>
        <span className="mt-2 text-[13px] font-medium text-ink-900">
          {file ? file.name : "Select a CSV file"}
        </span>
        <span className="mt-1 text-[11px] text-ink-400">
          UTF-8, up to 2 MB. One material stream per row.
        </span>
        <input
          id="csv-file"
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setError(null);
          }}
        />
      </label>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="label-mono mb-1.5 text-[8.5px] text-ink-400">Required columns</p>
          <ul className="space-y-0.5 font-mono text-[10.5px] text-ink-600">
            {REQUIRED.map((column) => (
              <li key={column}>{column}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label-mono mb-1.5 text-[8.5px] text-ink-400">Optional columns</p>
          <p className="font-mono text-[10.5px] leading-relaxed text-ink-500">
            {OPTIONAL.join(", ")}
          </p>
        </div>
      </div>

      <p className="mt-3 rounded-lg bg-paper-100 px-3 py-2.5 text-[10.5px] leading-relaxed text-ink-400">
        Rows are validated individually: invalid rows are reported with their line number and the
        rest of the batch still imports. Reference codes must be unique.
      </p>

      {error ? (
        <div className="mt-3 rounded-lg border border-rust-500/30 bg-rust-500/[0.06] px-3 py-2 text-[11.5px] text-rust-500">
          {error}
        </div>
      ) : null}

      <div className="mt-5 flex items-center justify-between border-t border-paper-200 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-2 text-[11.5px] text-ink-500 hover:text-ink-900"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={!file || busy}
          className="rounded-lg bg-forest-900 px-3.5 py-2 text-[11.5px] font-medium text-paper-50 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Importing…" : "Import streams"}
        </button>
      </div>
    </div>
  );
}
