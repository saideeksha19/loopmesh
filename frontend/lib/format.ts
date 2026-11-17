import type { UnitQuantity } from "@/lib/types";

const UNIT_LABELS: Record<string, string> = {
  kg: "kg",
  tonne: "t",
  m3: "m³",
  litre: "L",
  mwh: "MWh",
};

const UNIT_NAMES: Record<string, string> = {
  kg: "kilograms",
  tonne: "tonnes",
  m3: "cubic metres",
  litre: "litres",
  mwh: "megawatt hours",
};

export function unitLabel(unit: string): string {
  return UNIT_LABELS[unit] ?? unit;
}

export function unitName(unit: string): string {
  return UNIT_NAMES[unit] ?? unit;
}

export function formatNumber(value: number, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value);
}

export function formatQuantity(value: number, unit: string): string {
  const fractionDigits = Math.abs(value) < 10 ? 2 : 0;
  return `${formatNumber(value, fractionDigits)} ${unitLabel(unit)}`;
}

export function primaryQuantity(
  quantities: UnitQuantity[],
): { formatted: string; note: string | null } {
  if (!quantities.length) return { formatted: "0", note: null };
  const primary = quantities[0];
  const others = quantities.slice(1);
  return {
    formatted: formatNumber(primary.quantity, primary.quantity < 10 ? 2 : 0),
    note: others.length
      ? `+ ${others.map((item) => formatQuantity(item.quantity, item.unit)).join(" · ")}`
      : unitLabel(primary.unit),
  };
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatDateWindow(start: string | null, end: string | null): string {
  if (!start && !end) return "No window declared";
  const from = start ? formatDate(start) : "open";
  const to = end ? formatDate(end) : "open";
  return `${from} → ${to}`;
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatDate(value);
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function sectorLabel(value: string): string {
  const overrides: Record<string, string> = {
    steel_metals: "Steel & metals",
    cement_minerals: "Cement & minerals",
    plastics_polymers: "Plastics & polymers",
    food_agriculture: "Food & agriculture",
    glass_ceramics: "Glass & ceramics",
    paper_packaging: "Paper & packaging",
    energy_utilities: "Energy & utilities",
    water_treatment: "Water treatment",
  };
  return overrides[value] ?? titleCase(value);
}

export function categoryTone(category: string): string {
  const tones: Record<string, string> = {
    metals: "bg-forest-800",
    minerals: "bg-forest-600",
    polymers: "bg-teal-500",
    organics: "bg-lime-500",
    chemicals: "bg-clay-500",
    glass: "bg-forest-500",
    paper: "bg-paper-300",
    textiles: "bg-rust-500",
    water: "bg-teal-500",
    energy: "bg-lime-400",
    other: "bg-ink-300",
  };
  return tones[category] ?? "bg-ink-300";
}
