"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AddMaterialForm } from "@/components/materials/add-material-form";
import { CsvImport } from "@/components/materials/csv-import";
import { MaterialDrawer } from "@/components/materials/material-drawer";
import { ArrowUpRight, PlusIcon, SearchIcon, UploadIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { getJson } from "@/lib/client-api";
import { formatQuantity, titleCase } from "@/lib/format";
import type {
  CsvImportReport,
  MaterialDetail,
  MaterialSummary,
  OrganizationSummary,
} from "@/lib/types";

const inputClass =
  "rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-2 text-[12px] text-ink-900 outline-none transition-colors placeholder:text-ink-300 focus:border-forest-600 focus:bg-white";

export function MaterialsWorkspace({
  initialMaterials,
  organizations,
  initialCategory,
  canCreate,
  canImport,
}: {
  initialMaterials: MaterialSummary[];
  organizations: OrganizationSummary[];
  initialCategory?: string;
  canCreate: boolean;
  canImport: boolean;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(initialCategory ?? "all");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MaterialDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [report, setReport] = useState<CsvImportReport | null>(null);
  const rowButtons = useRef(new Map<string, HTMLButtonElement>());

  const categories = useMemo(
    () => Array.from(new Set(initialMaterials.map((material) => material.category))).sort(),
    [initialMaterials],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return initialMaterials.filter((material) => {
      if (category !== "all" && material.category !== category) return false;
      if (status !== "all" && material.status !== status) return false;
      if (!needle) return true;
      return (
        material.name.toLowerCase().includes(needle) ||
        material.reference_code.toLowerCase().includes(needle) ||
        material.organization.name.toLowerCase().includes(needle)
      );
    });
  }, [initialMaterials, query, category, status]);

  async function openMaterial(id: string) {
    setSelectedId(id);
    setDetailLoading(true);
    setDetail(null);
    const result = await getJson<MaterialDetail>(`/materials/${id}`);
    setDetailLoading(false);
    if (result.ok) setDetail(result.data);
  }

  function closeDrawer() {
    const origin = selectedId ? rowButtons.current.get(selectedId) : undefined;
    setSelectedId(null);
    setDetail(null);
    origin?.focus();
  }

  function refresh() {
    router.refresh();
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, reference or organisation"
            className={`${inputClass} w-full pl-8`}
            aria-label="Search material streams"
          />
        </div>

        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="Filter by category"
          className={inputClass}
        >
          <option value="all">All categories</option>
          {categories.map((item) => (
            <option key={item} value={item}>
              {titleCase(item)}
            </option>
          ))}
        </select>

        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="Filter by status"
          className={inputClass}
        >
          <option value="all">All statuses</option>
          <option value="available">Available</option>
          <option value="reserved">Reserved</option>
          <option value="committed">Committed</option>
          <option value="archived">Archived</option>
        </select>

        {canImport || canCreate ? (
          <div className="ml-auto flex items-center gap-2">
            {canImport ? (
              <button
                type="button"
                onClick={() => setImportOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-2 text-[11.5px] font-medium text-ink-700 transition-colors hover:bg-paper-100"
              >
                <UploadIcon className="h-4 w-4" /> Import CSV
              </button>
            ) : null}
            {canCreate ? (
              <button
                type="button"
                onClick={() => setAddOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-forest-900 px-3 py-2 text-[11.5px] font-medium text-paper-50 transition-colors hover:bg-forest-800"
              >
                <PlusIcon className="h-4 w-4" /> Add material
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {report ? (
        <div className="mb-4 rounded-xl border border-forest-600/25 bg-forest-800/[0.05] px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <p className="text-[12px] font-medium text-forest-800">
              Imported {report.created} of {report.rows_received} rows
            </p>
            <p className="font-mono text-[10.5px] text-ink-500">{report.filename}</p>
            {report.skipped ? (
              <Badge tone="warning">{report.skipped} skipped</Badge>
            ) : (
              <Badge tone="lime">no row errors</Badge>
            )}
            <button
              type="button"
              onClick={() => setReport(null)}
              className="ml-auto text-[10.5px] text-ink-400 hover:text-ink-700"
            >
              Dismiss
            </button>
          </div>
          {report.errors.length ? (
            <ul className="mt-2 space-y-0.5 font-mono text-[10.5px] text-rust-500">
              {report.errors.slice(0, 6).map((rowError) => (
                <li key={`${rowError.row}-${rowError.message}`}>
                  row {rowError.row}: {rowError.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-paper-200 px-4 py-2.5">
          <p className="label-mono text-[8.5px] text-ink-400">
            {filtered.length} of {initialMaterials.length} streams
          </p>
          <p className="hidden font-mono text-[9.5px] text-ink-300 sm:block">
            structured intake only · no image inference
          </p>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            title="No streams match these filters"
            description="Adjust the search or register a new stream. Every profile needs a declared quantity, unit and organisation."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] border-collapse text-left">
              <thead>
                <tr className="border-b border-paper-200 bg-paper-50/60">
                  {["Reference", "Material", "Organisation", "Category", "Condition", "Available", "Source", ""].map(
                    (heading) => (
                      <th
                        key={heading}
                        className="label-mono px-4 py-2.5 text-[8.5px] font-normal text-ink-400"
                      >
                        {heading}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {filtered.map((material) => {
                  const selected = material.id === selectedId;
                  return (
                    <tr
                      key={material.id}
                      className={`row-hover cursor-pointer border-b border-paper-200/70 last:border-0 ${
                        selected ? "bg-paper-100" : ""
                      }`}
                      onClick={() => openMaterial(material.id)}
                    >
                      <td className="px-4 py-2.5 font-mono text-[10px] tracking-wide text-ink-400">
                        {material.reference_code}
                      </td>
                      <td className="px-4 py-2.5">
                        <button
                          type="button"
                          ref={(node) => {
                            if (node) rowButtons.current.set(material.id, node);
                            else rowButtons.current.delete(material.id);
                          }}
                          onClick={(event) => {
                            event.stopPropagation();
                            void openMaterial(material.id);
                          }}
                          aria-haspopup="dialog"
                          aria-label={`Open material detail: ${material.name} (${material.reference_code})`}
                          className="block text-left"
                        >
                          <span className="block text-[12.5px] font-medium text-ink-900">
                            {material.name}
                          </span>
                          <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-ink-400">
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                material.status === "available" ? "bg-forest-600" : "bg-ink-300"
                              }`}
                            />
                            {material.status}
                            {material.hazard_class ? ` · ${material.hazard_class}` : ""}
                          </span>
                        </button>
                      </td>
                      <td className="px-4 py-2.5 text-[11.5px] text-ink-600">
                        {material.organization.name}
                        <span className="block text-[10px] text-ink-300">
                          {material.organization.city ?? material.organization.country}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge tone="forest">{titleCase(material.category)}</Badge>
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-ink-500">
                        {titleCase(material.condition)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span className="figure text-[12px] text-ink-900">
                          {formatQuantity(material.quantity_available, material.unit)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge tone={material.data_source === "demo" ? "muted" : "neutral"} mono>
                          {material.data_source}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ArrowUpRight aria-hidden="true" className="ml-auto h-4 w-4 text-ink-300" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedId ? (
        <MaterialDrawer material={detail} loading={detailLoading} onClose={closeDrawer} />
      ) : null}

      <Modal
        open={canCreate && addOpen}
        onClose={() => setAddOpen(false)}
        title="Register a material stream"
        description="Structured profile used by the deterministic compatibility engine. Measurements without a declared source stay unknown."
      >
        <AddMaterialForm
          organizations={organizations}
          onCancel={() => setAddOpen(false)}
          onCreated={() => {
            setAddOpen(false);
            refresh();
          }}
        />
      </Modal>

      <Modal
        open={canImport && importOpen}
        onClose={() => setImportOpen(false)}
        title="Import material streams"
        description="Bulk intake from a structured CSV. Each row becomes one material profile."
        width="max-w-xl"
      >
        <CsvImport
          onCancel={() => setImportOpen(false)}
          onImported={(imported) => {
            setImportOpen(false);
            setReport(imported);
            refresh();
          }}
        />
      </Modal>
    </>
  );
}
