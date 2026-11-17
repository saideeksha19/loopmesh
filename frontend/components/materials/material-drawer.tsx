"use client";

import { useEffect, useRef } from "react";

import { CloseIcon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { formatDateWindow, formatQuantity, titleCase } from "@/lib/format";
import type { MaterialDetail } from "@/lib/types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-paper-200 py-2.5">
      <dt className="label-mono text-[8.5px] text-ink-400">{label}</dt>
      <dd className="mt-1 text-[12px] leading-snug text-ink-700">{value}</dd>
    </div>
  );
}

export function MaterialDrawer({
  material,
  loading,
  onClose,
}: {
  material: MaterialDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 bg-forest-950/40 backdrop-blur-[2px]"
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={material ? `Material detail: ${material.name}` : "Material detail"}
        tabIndex={-1}
        className="animate-drawer relative flex h-full w-full max-w-[460px] flex-col border-l border-paper-200 bg-[#fffdf8] shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-paper-200 px-5 py-4">
          <div className="min-w-0">
            <p className="label-mono text-[9px] text-ink-400">
              {material?.reference_code ?? "Loading"}
            </p>
            <h2 className="mt-1 truncate text-[16px] font-semibold text-ink-900">
              {material?.name ?? "Loading material…"}
            </h2>
            {material ? (
              <p className="mt-1 text-[11.5px] text-ink-500">{material.organization.name}</p>
            ) : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-paper-200 text-ink-500 hover:bg-paper-100"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>

        {loading || !material ? (
          <div className="flex flex-1 items-center justify-center text-[12px] text-ink-400">
            Loading specification…
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge tone="forest">{titleCase(material.category)}</Badge>
              <Badge tone="neutral">{titleCase(material.condition)}</Badge>
              <Badge tone={material.status === "available" ? "lime" : "outline"}>
                {titleCase(material.status)}
              </Badge>
              <Badge tone="muted" mono>
                {material.data_source === "demo" ? "demo data" : material.data_source}
              </Badge>
            </div>

            <div className="mt-4 rounded-xl border border-forest-800 bg-forest-900 px-4 py-3.5 text-paper-100">
              <p className="label-mono text-[8.5px] text-forest-500">Available quantity</p>
              <p className="figure mt-1.5 text-[24px] text-paper-50">
                {formatQuantity(material.quantity_available, material.unit)}
              </p>
              <p className="mt-1 text-[10.5px] text-forest-500">
                {material.hazard_class ? `Hazard: ${material.hazard_class}` : "Hazard class not declared"}
              </p>
            </div>

            <h3 className="label-mono mt-5 text-[9px] text-ink-400">Specification</h3>
            {material.specification ? (
              <>
                <dl className="mt-1.5 grid grid-cols-2 gap-x-4">
                  <Field
                    label="Purity"
                    value={
                      material.specification.purity_pct !== null
                        ? `${material.specification.purity_pct.toFixed(1)} %`
                        : "not assayed"
                    }
                  />
                  <Field
                    label="Contamination"
                    value={
                      material.specification.contamination_pct !== null
                        ? `${material.specification.contamination_pct.toFixed(1)} %`
                        : "not assayed"
                    }
                  />
                  <Field
                    label="Moisture"
                    value={
                      material.specification.moisture_pct !== null
                        ? `${material.specification.moisture_pct.toFixed(1)} %`
                        : "not declared"
                    }
                  />
                  <Field
                    label="pH"
                    value={
                      material.specification.ph_value !== null
                        ? material.specification.ph_value.toFixed(1)
                        : "—"
                    }
                  />
                  <Field
                    label="Calorific value"
                    value={
                      material.specification.calorific_value_mj_kg !== null
                        ? `${material.specification.calorific_value_mj_kg.toFixed(1)} MJ/kg`
                        : "—"
                    }
                  />
                  <Field
                    label="Assay method"
                    value={material.specification.assay_method ?? "Not stated"}
                  />
                </dl>

                {material.specification.composition.length ? (
                  <div className="mt-3">
                    <p className="label-mono text-[8.5px] text-ink-400">Composition</p>
                    <div className="mt-2 space-y-2">
                      {material.specification.composition.map((entry) => (
                        <div key={entry.substance}>
                          <div className="flex justify-between text-[11px] text-ink-600">
                            <span>{entry.substance}</span>
                            <span className="figure text-ink-500">{entry.pct}%</span>
                          </div>
                          <div className="mt-1 h-1 overflow-hidden rounded-full bg-paper-200">
                            <div
                              className="h-full rounded-full bg-forest-600"
                              style={{ width: `${Math.min(100, entry.pct)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {Object.keys(material.specification.contaminants).length ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {Object.entries(material.specification.contaminants).map(([name, pct]) => (
                      <Badge key={name} tone="warning" mono>
                        {name} {pct}%
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="mt-2 rounded-lg border border-dashed border-paper-300 bg-paper-50 px-3 py-3 text-[11.5px] leading-relaxed text-ink-500">
                No specification on file. The compatibility engine will treat every measurement as
                unknown and return <span className="font-medium text-ink-700">unverified</span>,
                never compatible.
              </div>
            )}

            <h3 className="label-mono mt-5 text-[9px] text-ink-400">Handling & logistics</h3>
            <dl className="mt-1.5">
              <Field label="Handling requirements" value={material.handling_requirements ?? "None declared"} />
              <Field label="Origin process" value={material.origin_process ?? "Not stated"} />
              <Field
                label="Availability window"
                value={formatDateWindow(material.availability_start, material.availability_end)}
              />
              <Field label="Linked opportunities" value={`${material.opportunity_count}`} />
            </dl>

            {material.description ? (
              <p className="mt-4 border-t border-paper-200 pt-3 text-[11.5px] leading-relaxed text-ink-500">
                {material.description}
              </p>
            ) : null}

            <p className="mt-4 rounded-lg bg-paper-100 px-3 py-2.5 text-[10.5px] leading-relaxed text-ink-400">
              Source: {material.data_source === "demo" ? "demo seed dataset" : material.data_source}.
              Measurements are declarations supplied through structured forms or CSV, never inferred
              from images.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
