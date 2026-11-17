"use client";

import { useState } from "react";

import { postJson } from "@/lib/client-api";
import type { MaterialDetail, OrganizationSummary } from "@/lib/types";

const CATEGORIES = [
  "metals",
  "polymers",
  "minerals",
  "organics",
  "chemicals",
  "glass",
  "paper",
  "textiles",
  "water",
  "energy",
  "other",
];

const UNITS = ["tonne", "kg", "m3", "litre", "mwh"];
const CONDITIONS = ["as_generated", "processed", "aged", "degraded", "mixed", "unknown"];

type FormState = {
  organization_id: string;
  reference_code: string;
  name: string;
  category: string;
  quantity_available: string;
  unit: string;
  condition: string;
  hazard_class: string;
  origin_process: string;
  description: string;
  handling_requirements: string;
  availability_start: string;
  availability_end: string;
  purity_pct: string;
  contamination_pct: string;
  moisture_pct: string;
  ph_value: string;
  assay_method: string;
};

const INITIAL: FormState = {
  organization_id: "",
  reference_code: "",
  name: "",
  category: "metals",
  quantity_available: "",
  unit: "tonne",
  condition: "as_generated",
  hazard_class: "non_hazardous",
  origin_process: "",
  description: "",
  handling_requirements: "",
  availability_start: "",
  availability_end: "",
  purity_pct: "",
  contamination_pct: "",
  moisture_pct: "",
  ph_value: "",
  assay_method: "",
};

const inputClass =
  "w-full rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-2 text-[12px] text-ink-900 outline-none transition-colors placeholder:text-ink-300 focus:border-forest-600 focus:bg-white";
const labelClass = "label-mono mb-1.5 block text-[8.5px] text-ink-400";

function numericOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function AddMaterialForm({
  organizations,
  onCreated,
  onCancel,
}: {
  organizations: OrganizationSummary[];
  onCreated: (material: MaterialDetail) => void;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<1 | 2>(1);
  const [form, setForm] = useState<FormState>({
    ...INITIAL,
    organization_id: organizations[0]?.id ?? "",
    reference_code: `LM-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<string[]>([]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  const stepOneValid =
    Boolean(form.organization_id) &&
    form.reference_code.trim().length >= 2 &&
    form.name.trim().length >= 2 &&
    Number(form.quantity_available) > 0;

  async function submit() {
    setSubmitting(true);
    setError(null);
    setFieldErrors([]);

    const specification = {
      purity_pct: numericOrNull(form.purity_pct),
      contamination_pct: numericOrNull(form.contamination_pct),
      moisture_pct: numericOrNull(form.moisture_pct),
      ph_value: numericOrNull(form.ph_value),
      assay_method: form.assay_method.trim() || null,
      composition: [],
      contaminants: {},
    };
    const hasSpecification = Object.values(specification).some(
      (value) => value !== null && value !== "",
    );

    const payload = {
      organization_id: form.organization_id,
      reference_code: form.reference_code.trim(),
      name: form.name.trim(),
      category: form.category,
      quantity_available: Number(form.quantity_available),
      unit: form.unit,
      condition: form.condition,
      hazard_class: form.hazard_class.trim() || null,
      origin_process: form.origin_process.trim() || null,
      description: form.description.trim() || null,
      handling_requirements: form.handling_requirements.trim() || null,
      availability_start: form.availability_start || null,
      availability_end: form.availability_end || null,
      specification: hasSpecification ? specification : null,
    };

    const result = await postJson<MaterialDetail>("/materials", payload);
    setSubmitting(false);

    if (!result.ok) {
      setError(result.error);
      setFieldErrors(result.fields ?? []);
      return;
    }
    onCreated(result.data);
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        {[1, 2].map((value) => (
          <div key={value} className="flex flex-1 items-center gap-2">
            <span
              className={[
                "flex h-5 w-5 items-center justify-center rounded-full font-mono text-[10px]",
                step >= value
                  ? "bg-forest-900 text-lime-400"
                  : "border border-paper-300 text-ink-300",
              ].join(" ")}
            >
              {value}
            </span>
            <span
              className={`text-[11px] ${
                step === value ? "font-medium text-ink-900" : "text-ink-400"
              }`}
            >
              {value === 1 ? "Stream identity" : "Specification & handling"}
            </span>
            <span className="h-px flex-1 bg-paper-200" />
          </div>
        ))}
      </div>

      {step === 1 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="organization">
              Supplying organization
            </label>
            {organizations.length > 1 ? (
              <select
                id="organization"
                className={inputClass}
                value={form.organization_id}
                onChange={(event) => update("organization_id", event.target.value)}
              >
                {organizations.map((organization) => (
                  <option key={organization.id} value={organization.id}>
                    {organization.name}
                  </option>
                ))}
              </select>
            ) : (
              <p
                id="organization"
                className="flex h-[34px] items-center rounded-lg border border-paper-200 bg-paper-100 px-2.5 text-[12px] text-ink-700"
              >
                {organizations[0]?.name ?? "No active organisation"}
              </p>
            )}
          </div>

          <div>
            <label className={labelClass} htmlFor="reference_code">
              Reference code
            </label>
            <input
              id="reference_code"
              className={`${inputClass} font-mono`}
              value={form.reference_code}
              onChange={(event) => update("reference_code", event.target.value)}
              placeholder="LM-0042"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="category">
              Material category
            </label>
            <select
              id="category"
              className={inputClass}
              value={form.category}
              onChange={(event) => update("category", event.target.value)}
            >
              {CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </div>

          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="name">
              Material name
            </label>
            <input
              id="name"
              className={inputClass}
              value={form.name}
              onChange={(event) => update("name", event.target.value)}
              placeholder="Granulated blast furnace slag"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="quantity">
              Available quantity
            </label>
            <input
              id="quantity"
              type="number"
              min="0"
              step="0.001"
              className={`${inputClass} figure`}
              value={form.quantity_available}
              onChange={(event) => update("quantity_available", event.target.value)}
              placeholder="1200"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="unit">
              Unit
            </label>
            <select
              id="unit"
              className={inputClass}
              value={form.unit}
              onChange={(event) => update("unit", event.target.value)}
            >
              {UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelClass} htmlFor="condition">
              Condition
            </label>
            <select
              id="condition"
              className={inputClass}
              value={form.condition}
              onChange={(event) => update("condition", event.target.value)}
            >
              {CONDITIONS.map((condition) => (
                <option key={condition} value={condition}>
                  {condition}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelClass} htmlFor="hazard">
              Hazard class
            </label>
            <input
              id="hazard"
              className={inputClass}
              value={form.hazard_class}
              onChange={(event) => update("hazard_class", event.target.value)}
              placeholder="non_hazardous"
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="available_from">
              Available from
            </label>
            <input
              id="available_from"
              type="date"
              className={inputClass}
              value={form.availability_start}
              onChange={(event) => update("availability_start", event.target.value)}
            />
          </div>

          <div>
            <label className={labelClass} htmlFor="available_until">
              Available until
            </label>
            <input
              id="available_until"
              type="date"
              className={inputClass}
              value={form.availability_end}
              onChange={(event) => update("availability_end", event.target.value)}
            />
          </div>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass} htmlFor="purity">
              Purity %
            </label>
            <input
              id="purity"
              type="number"
              min="0"
              max="100"
              step="0.1"
              className={`${inputClass} figure`}
              value={form.purity_pct}
              onChange={(event) => update("purity_pct", event.target.value)}
              placeholder="94.0"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="contamination">
              Contamination %
            </label>
            <input
              id="contamination"
              type="number"
              min="0"
              max="100"
              step="0.1"
              className={`${inputClass} figure`}
              value={form.contamination_pct}
              onChange={(event) => update("contamination_pct", event.target.value)}
              placeholder="1.2"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="moisture">
              Moisture %
            </label>
            <input
              id="moisture"
              type="number"
              min="0"
              max="100"
              step="0.1"
              className={`${inputClass} figure`}
              value={form.moisture_pct}
              onChange={(event) => update("moisture_pct", event.target.value)}
              placeholder="8.0"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="ph">
              pH
            </label>
            <input
              id="ph"
              type="number"
              min="0"
              max="14"
              step="0.1"
              className={`${inputClass} figure`}
              value={form.ph_value}
              onChange={(event) => update("ph_value", event.target.value)}
              placeholder="7.2"
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="assay">
              Assay method / evidence source
            </label>
            <input
              id="assay"
              className={inputClass}
              value={form.assay_method}
              onChange={(event) => update("assay_method", event.target.value)}
              placeholder="Supplier laboratory certificate, Q4 2026"
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="origin">
              Origin process
            </label>
            <input
              id="origin"
              className={inputClass}
              value={form.origin_process}
              onChange={(event) => update("origin_process", event.target.value)}
              placeholder="Blast furnace granulation"
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="handling">
              Handling requirements
            </label>
            <textarea
              id="handling"
              rows={2}
              className={inputClass}
              value={form.handling_requirements}
              onChange={(event) => update("handling_requirements", event.target.value)}
              placeholder="Covered tipper, moisture sensitive."
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="description">
              Description
            </label>
            <textarea
              id="description"
              rows={2}
              className={inputClass}
              value={form.description}
              onChange={(event) => update("description", event.target.value)}
              placeholder="What the stream is and how it is generated."
            />
          </div>
          <p className="sm:col-span-2 rounded-lg bg-paper-100 px-3 py-2.5 text-[10.5px] leading-relaxed text-ink-400">
            Leaving a measurement blank keeps it unknown. The compatibility engine treats unknown
            as unverified rather than assuming suitability.
          </p>
        </div>
      )}

      {error ? (
        <div className="mt-3 rounded-lg border border-rust-500/30 bg-rust-500/[0.06] px-3 py-2 text-[11.5px] text-rust-500">
          <p>{error}</p>
          {fieldErrors.length ? (
            <ul className="mt-1 list-inside list-disc font-mono text-[10.5px]">
              {fieldErrors.map((fieldError) => (
                <li key={fieldError}>{fieldError}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="mt-5 flex items-center justify-between gap-2 border-t border-paper-200 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-2 text-[11.5px] text-ink-500 hover:text-ink-900"
        >
          Cancel
        </button>
        <div className="flex items-center gap-2">
          {step === 2 ? (
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rounded-lg border border-paper-300 bg-paper-50 px-3 py-2 text-[11.5px] font-medium text-ink-700 hover:bg-paper-100"
            >
              Back
            </button>
          ) : null}
          {step === 1 ? (
            <button
              type="button"
              disabled={!stepOneValid}
              onClick={() => setStep(2)}
              className="rounded-lg bg-forest-900 px-3.5 py-2 text-[11.5px] font-medium text-paper-50 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Continue
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="rounded-lg bg-forest-900 px-3.5 py-2 text-[11.5px] font-medium text-paper-50 transition-colors hover:bg-forest-800 disabled:opacity-50"
            >
              {submitting ? "Registering…" : "Register material"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
