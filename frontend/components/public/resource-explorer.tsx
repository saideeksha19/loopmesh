"use client";

import { useEffect, useMemo, useState } from "react";

type FlowType = "energy" | "water" | "material";

type Node = {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
};

type Edge = {
  id: string;
  from: string;
  to: string;
  flow: FlowType;
  label: string;
  detail: string;
};

const NODES: Node[] = [
  { id: "n1", label: "Manufacturing plant", kind: "Processor", x: 15, y: 30 },
  { id: "n2", label: "District heat user", kind: "Energy consumer", x: 50, y: 15 },
  { id: "n3", label: "Water treatment partner", kind: "Treatment", x: 85, y: 35 },
  { id: "n4", label: "Materials reprocessor", kind: "Reprocessor", x: 70, y: 75 },
  { id: "n5", label: "Food processor", kind: "Producer", x: 20, y: 80 },
];

const EDGES: Edge[] = [
  {
    id: "e1",
    from: "n1",
    to: "n2",
    flow: "energy",
    label: "Recoverable process heat",
    detail:
      "Illustrative example: surplus thermal output from a manufacturing process could be evaluated as a heat source for a nearby user, subject to temperature, timing, and contractual constraints.",
  },
  {
    id: "e2",
    from: "n1",
    to: "n3",
    flow: "water",
    label: "Treated process water stream",
    detail:
      "Illustrative example: water that meets defined quality parameters might be considered for reuse or transfer after compatibility and regulatory review.",
  },
  {
    id: "e3",
    from: "n5",
    to: "n4",
    flow: "material",
    label: "Organic by-product stream",
    detail:
      "Illustrative example: a consistent by-product could be screened as input for a reprocessor if composition, contamination, and logistics align.",
  },
  {
    id: "e4",
    from: "n1",
    to: "n4",
    flow: "material",
    label: "Sorted material residue",
    detail:
      "Illustrative example: separated residues might become feedstock elsewhere when material profiles and handling requirements match.",
  },
  {
    id: "e5",
    from: "n3",
    to: "n4",
    flow: "water",
    label: "Polished water for process use",
    detail:
      "Illustrative example: treated water could support specific operations if quality thresholds and availability windows are satisfied.",
  },
];

const FLOW_META: Record<FlowType, { label: string; color: string; ring: string; bg: string }> = {
  energy: { label: "Energy", color: "text-lime-200", ring: "ring-lime-400/60", bg: "bg-lime-400/15 border-lime-400/40" },
  water: { label: "Water", color: "text-teal-100", ring: "ring-teal-400/60", bg: "bg-teal-400/15 border-teal-400/40" },
  material: { label: "Materials", color: "text-amber-100", ring: "ring-amber-400/60", bg: "bg-amber-400/15 border-amber-400/40" },
};

export function ResourceExplorer() {
  const [flowFilter, setFlowFilter] = useState<FlowType | "all">("all");
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  const visibleEdges = useMemo(() => {
    return EDGES.filter((e) => (flowFilter === "all" ? true : e.flow === flowFilter));
  }, [flowFilter]);

  const highlightedNodeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const e of visibleEdges) {
      ids.add(e.from);
      ids.add(e.to);
    }
    if (selectedNode) ids.add(selectedNode);
    return ids;
  }, [visibleEdges, selectedNode]);

  const nodeById = useMemo(() => new Map(NODES.map((n) => [n.id, n])), []);

  const selectedEdge = useMemo(() => {
    if (!selectedNode) return null;
    // Prefer an edge connected to selected node that is visible under current filter
    return visibleEdges.find((e) => e.from === selectedNode || e.to === selectedNode) ?? null;
  }, [selectedNode, visibleEdges]);

  const selectedNodeData = selectedNode ? nodeById.get(selectedNode) ?? null : null;

  return (
    <div className="mt-10">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by resource flow">
          <button
            type="button"
            onClick={() => setFlowFilter("all")}
            className={[
              "rounded-full border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60",
              flowFilter === "all"
                ? "border-paper-50/30 bg-paper-50/10 text-paper-50"
                : "border-forest-600/70 bg-forest-900/40 text-forest-200 hover:text-paper-50",
            ].join(" ")}
          >
            All flows
          </button>
          {(["energy", "water", "material"] as FlowType[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFlowFilter(f)}
              className={[
                "rounded-full border px-4 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60",
                flowFilter === f ? FLOW_META[f].bg + " " + FLOW_META[f].color : "border-forest-600/70 bg-forest-900/40 text-forest-200 hover:text-paper-50",
              ].join(" ")}
            >
              {FLOW_META[f].label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => {
            setFlowFilter("all");
            setSelectedNode(null);
          }}
          className="rounded-lg border border-forest-600/70 px-3 py-2 text-[11px] text-forest-200 hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60"
        >
          Reset view
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-start">
        <div className="relative overflow-hidden rounded-2xl border border-forest-700/60 bg-forest-950/60 p-4 sm:p-6">
          <p className="label-mono text-[9px] text-forest-400">Illustrative ecosystem (select a node)</p>
          <div className="relative mt-4 h-[360px] w-full sm:h-[420px]">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
              {visibleEdges.map((e) => {
                const a = nodeById.get(e.from);
                const b = nodeById.get(e.to);
                if (!a || !b) return null;
                const isFocused = selectedNode && (e.from === selectedNode || e.to === selectedNode);
                const stroke =
                  e.flow === "energy" ? "#c6f35c" : e.flow === "water" ? "#5eead4" : "#fbbf24";
                return (
                  <line
                    key={e.id}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={stroke}
                    strokeWidth={isFocused ? 1.2 : 0.6}
                    strokeOpacity={isFocused ? 0.95 : 0.45}
                    strokeDasharray={reducedMotion ? "none" : "2 3"}
                    className={reducedMotion ? "" : "animate-[dash-flow_6s_linear_infinite]"}
                  />
                );
              })}
            </svg>
            {NODES.map((n) => {
              const isDim = flowFilter !== "all" && !highlightedNodeIds.has(n.id) && !selectedNode;
              const isSelected = selectedNode === n.id;
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => setSelectedNode((cur) => (cur === n.id ? null : n.id))}
                  className={[
                    "absolute -translate-x-1/2 -translate-y-1/2 rounded-xl border px-3 py-2 text-left backdrop-blur-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/70",
                    isSelected
                      ? "border-lime-400/80 bg-lime-400/15 ring-2 " + "ring-lime-400/50"
                      : "border-forest-600/70 bg-forest-900/70 hover:border-lime-400/40",
                    isDim ? "opacity-35" : "opacity-100",
                  ].join(" ")}
                  style={{ left: `${n.x}%`, top: `${n.y}%` }}
                  aria-pressed={isSelected}
                  aria-label={`${n.label}, ${n.kind}`}
                >
                  <span className="block text-[11px] font-medium text-paper-50">{n.label}</span>
                  <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wider text-forest-300">{n.kind}</span>
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-[10.5px] leading-relaxed text-forest-400">
            Illustrative only. Connections and facility roles are examples, not real operational data from this deployment.
          </p>
        </div>

        <div className="rounded-2xl border border-forest-700/60 bg-forest-950/60 p-5 sm:p-6">
          <p className="label-mono text-[9px] text-forest-400">Detail panel</p>
          {selectedNodeData ? (
            <div className="mt-4">
              <h3 className="text-[16px] font-semibold text-paper-50">{selectedNodeData.label}</h3>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-forest-300">{selectedNodeData.kind}</p>
              {selectedEdge ? (
                <div className="mt-5 rounded-xl border border-forest-600/60 bg-forest-900/50 p-4">
                  <div className="flex items-center gap-2">
                    <span className={["inline-flex rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider", FLOW_META[selectedEdge.flow].bg, FLOW_META[selectedEdge.flow].color].join(" ")}>
                      {FLOW_META[selectedEdge.flow].label}
                    </span>
                  </div>
                  <p className="mt-3 text-[12.5px] font-medium text-paper-100">{selectedEdge.label}</p>
                  <p className="mt-2 text-[12px] leading-relaxed text-forest-100/80">{selectedEdge.detail}</p>
                </div>
              ) : (
                <p className="mt-5 text-[12px] leading-relaxed text-forest-100/75">
                  No highlighted illustrative exchange matches the current flow filter for this node. Try “All flows” or select another node.
                </p>
              )}
              <p className="mt-5 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[10.5px] leading-relaxed text-amber-100/90">
                Labeled illustrative: this panel describes a hypothetical exchange pattern, not measured savings, prices, emissions, or confirmed operational outcomes.
              </p>
            </div>
          ) : (
            <div className="mt-4">
              <p className="text-[13px] leading-relaxed text-forest-100/80">
                Select a facility node in the map to view an illustrative resource exchange. Use the flow filters to focus on energy, water, or materials.
              </p>
              <p className="mt-4 text-[10.5px] leading-relaxed text-forest-400">
                All examples are illustrative and do not represent real LoopMesh operational results.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
