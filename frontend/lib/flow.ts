export type FlowKind = "energy" | "water" | "material";

export function flowKindForCategory(category: string): FlowKind {
  const key = category.toLowerCase();
  if (key === "energy") return "energy";
  if (key === "water") return "water";
  return "material";
}

export function flowColor(kind: FlowKind): string {
  if (kind === "energy") return "var(--color-flow-energy)";
  if (kind === "water") return "var(--color-flow-water)";
  return "var(--color-flow-material)";
}

export function flowLabel(kind: FlowKind): string {
  if (kind === "energy") return "Energy";
  if (kind === "water") return "Water";
  return "Material";
}
