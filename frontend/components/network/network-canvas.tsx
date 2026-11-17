"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { flowColor, flowKindForCategory, flowLabel } from "@/lib/flow";
import { formatQuantity, sectorLabel, titleCase } from "@/lib/format";
import type { NetworkEdge, NetworkGraph, NetworkNode } from "@/lib/types";

const WIDTH = 1000;
const HEIGHT = 600;

type Point = { x: number; y: number; vx: number; vy: number };

/** Deterministic layout: seeded circle + fixed-iteration spring/repulsion. */
function computePositions(nodes: NetworkNode[], edges: NetworkEdge[]): Record<string, Point> {
  const points: Record<string, Point> = {};
  const count = Math.max(nodes.length, 1);
  nodes.forEach((node, index) => {
    const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
    points[node.id] = {
      x: WIDTH / 2 + 330 * Math.cos(angle),
      y: HEIGHT / 2 + 215 * Math.sin(angle),
      vx: 0,
      vy: 0,
    };
  });

  const ids = nodes.map((node) => node.id);
  for (let iteration = 0; iteration < 280; iteration += 1) {
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const a = points[ids[i]];
        const b = points[ids[j]];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 1) {
          dx = (i - j) * 0.7;
          dy = 0.5;
          distance = Math.hypot(dx, dy) || 1;
        }
        const force = 26000 / (distance * distance);
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    for (const edge of edges) {
      const a = points[edge.source];
      const b = points[edge.target];
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.hypot(dx, dy) || 1;
      const force = (distance - 205) * 0.011;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }

    for (const id of ids) {
      const point = points[id];
      point.vx += (WIDTH / 2 - point.x) * 0.0016;
      point.vy += (HEIGHT / 2 - point.y) * 0.0022;
      point.vx *= 0.86;
      point.vy *= 0.86;
      point.x = Math.min(WIDTH - 60, Math.max(60, point.x + point.vx));
      point.y = Math.min(HEIGHT - 55, Math.max(55, point.y + point.vy));
    }
  }
  return points;
}

function radiusFor(node: NetworkNode): number {
  const links = node.inbound_links + node.outbound_links;
  return 11 + Math.min(9, links * 2.1);
}

export function NetworkCanvas({ graph }: { graph: NetworkGraph }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [flowFilter, setFlowFilter] = useState<"all" | "energy" | "water" | "material">("all");

  // SVG <g> elements are focused by Tab but do not match :focus/:focus-visible and
  // do not receive focus events in every browser, so the keyboard focus ring is
  // state-driven: it tracks document.activeElement after keyboard input only.
  useEffect(() => {
    let pending = 0;
    const KEYBOARD_KEYS = new Set([
      "Tab",
      "Enter",
      " ",
      "ArrowUp",
      "ArrowDown",
      "ArrowLeft",
      "ArrowRight",
    ]);

    const syncFocusRing = () => {
      const active = document.activeElement;
      setFocused(active instanceof Element ? active.getAttribute("data-node-id") : null);
    };

    const onPointerDown = () => {
      window.clearTimeout(pending);
      setFocused(null);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (!KEYBOARD_KEYS.has(event.key)) return;
      window.clearTimeout(pending);
      // activeElement settles after the key's default action has run.
      pending = window.setTimeout(syncFocusRing, 0);
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.clearTimeout(pending);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, []);

  const positions = useMemo(
    () => computePositions(graph.nodes, graph.edges),
    [graph.nodes, graph.edges],
  );

  const edges = useMemo(() => {
    let list = graph.edges;
    if (confirmedOnly) list = list.filter((edge) => edge.status === "confirmed");
    if (flowFilter !== "all") list = list.filter((edge) => flowKindForCategory(edge.category) === flowFilter);
    return list;
  }, [graph.edges, confirmedOnly, flowFilter]);

  const activeId = hovered ?? selected;
  const adjacent = useMemo(() => {
    const set = new Set<string>();
    if (!activeId) return set;
    for (const edge of edges) {
      if (edge.source === activeId) set.add(edge.target);
      if (edge.target === activeId) set.add(edge.source);
    }
    return set;
  }, [activeId, edges]);

  const selectedNode = graph.nodes.find((node) => node.id === selected) ?? null;
  const selectedFlows = graph.edges.filter(
    (edge) => edge.source === selected || edge.target === selected,
  );

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="panel relative overflow-hidden">
        <style>{`
          @keyframes net-dash { to { stroke-dashoffset: -24; } }
        `}</style>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-paper-200/80 px-4 py-3">
          <div>
            <p className="label-mono text-[8.5px] text-ink-400">
              {graph.summary.organizations} nodes · {edges.length} visible lanes
            </p>
            <p className="mt-0.5 text-[11px] text-ink-500">Hover or select to inspect flows, direction and verification status.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-paper-300/70 bg-paper-50 p-1">
              {(["all", "energy", "water", "material"] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setFlowFilter(kind)}
                  className={[
                    "rounded-md px-2.5 py-1 font-mono text-[9px] uppercase tracking-wide transition-premium",
                    flowFilter === kind ? "bg-forest-900 text-paper-50" : "text-ink-500 hover:bg-paper-100",
                  ].join(" ")}
                >
                  {kind === "all" ? "All flows" : kind}
                </button>
              ))}
            </div>
            <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-paper-300/70 bg-paper-50 px-2.5 py-1.5 font-mono text-[9px] tracking-wide text-ink-500 transition-premium hover:bg-paper-100">
              <input
                type="checkbox"
                checked={confirmedOnly}
                onChange={(event) => setConfirmedOnly(event.target.checked)}
                className="h-3 w-3 accent-forest-700"
              />
              verified only
            </label>
          </div>
        </div>

        <div className="tech-grid relative">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(198,243,92,0.08),transparent_45%),radial-gradient(ellipse_at_80%_70%,rgba(79,168,154,0.08),transparent_40%)]" aria-hidden />
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="relative h-[500px] w-full sm:h-[560px]"
            role="img"
            aria-label="Resource network graph of organisations and material lanes"
          >
            <defs>
              <filter id="nodeShadow" x="-50%" y="-50%" width="200%" height="200%">
                <feDropShadow dx="0" dy="3" stdDeviation="4" floodOpacity="0.14" />
              </filter>
              <filter id="flowGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {edges.map((edge) => {
              const source = positions[edge.source];
              const target = positions[edge.target];
              if (!source || !target) return null;
              const confirmed = edge.status === "confirmed";
              const kind = flowKindForCategory(edge.category);
              const color = flowColor(kind);
              const isActive =
                activeId === null || edge.source === activeId || edge.target === activeId;
              const midX = (source.x + target.x) / 2;
              const midY = (source.y + target.y) / 2;
              const dx = target.x - source.x;
              const dy = target.y - source.y;
              const length = Math.hypot(dx, dy) || 1;
              const curve = 18;
              const controlX = midX - (dy / length) * curve;
              const controlY = midY + (dx / length) * curve;
              const d = `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`;

              return (
                <g key={edge.id}>
                  <path
                    d={d}
                    fill="none"
                    stroke={color}
                    strokeWidth={confirmed ? 2.6 : 1.3}
                    strokeOpacity={!isActive ? 0.08 : confirmed ? 0.92 : 0.3}
                    strokeDasharray={confirmed ? undefined : "5 6"}
                    style={!confirmed && isActive ? { animation: "net-dash 2.6s linear infinite" } : undefined}
                  />
                  {confirmed && isActive ? (
                    <>
                      <path d={d} fill="none" stroke={color} strokeWidth={5} strokeOpacity={0.1} filter="url(#flowGlow)" />
                      <circle r={3.2} fill={color}>
                        <animateMotion dur="3.4s" repeatCount="indefinite" path={d} />
                      </circle>
                    </>
                  ) : null}
                </g>
              );
            })}

            {graph.nodes.map((node) => {
              const point = positions[node.id];
              if (!point) return null;
              const radius = radiusFor(node);
              const isSupplier = node.material_streams > 0;
              const isActive = activeId === node.id;
              const isNeighbour = adjacent.has(node.id);
              const dimmed = activeId !== null && !isActive && !isNeighbour;
              const hasConfirmed = graph.edges.some(
                (edge) =>
                  edge.status === "confirmed" &&
                  (edge.source === node.id || edge.target === node.id),
              );

              return (
                <g
                  key={node.id}
                  transform={`translate(${point.x} ${point.y})`}
                  opacity={dimmed ? 0.28 : 1}
                  className="net-node cursor-pointer"
                  onMouseEnter={() => setHovered(node.id)}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => setSelected(node.id === selected ? null : node.id)}
                  role="button"
                  tabIndex={0}
                  data-node-id={node.id}
                  aria-pressed={selected === node.id}
                  aria-label={`${node.name}, ${node.material_streams} streams, ${node.outbound_links} outbound lanes`}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(node.id === selected ? null : node.id);
                    }
                  }}
                >
                  <circle r={radius + 8} fill="var(--color-lime-400)" opacity={isActive ? 0.12 : 0} />
                  <circle
                    r={radius}
                    fill={isSupplier ? "var(--color-forest-900)" : "var(--color-paper-50)"}
                    stroke={
                      isActive
                        ? "var(--color-lime-400)"
                        : hasConfirmed
                          ? "var(--color-lime-500)"
                          : node.open_demands > 0
                            ? "var(--color-forest-600)"
                            : "var(--color-paper-300)"
                    }
                    strokeWidth={isActive ? 2.6 : 1.5}
                    filter="url(#nodeShadow)"
                  />
                  <circle
                    className="net-node-focus-ring pointer-events-none"
                    r={radius + 6}
                    fill="none"
                    stroke="var(--color-lime-400)"
                    strokeWidth={2}
                    opacity={focused === node.id ? 1 : 0}
                  />
                  {isSupplier ? (
                    <circle r={2.2} fill="var(--color-lime-400)" />
                  ) : (
                    <circle r={2} fill="var(--color-forest-600)" opacity={0.6} />
                  )}
                  <text y={radius + 14} textAnchor="middle" className="pointer-events-none select-none" fill="var(--color-ink-700)" fontSize={10.5} fontWeight={isActive ? 600 : 500}>
                    {node.name.length > 20 ? `${node.name.slice(0, 19)}…` : node.name}
                  </text>
                  <text y={radius + 25} textAnchor="middle" className="pointer-events-none select-none" fill="var(--color-ink-400)" fontSize={8.5} fontFamily="var(--font-mono)" letterSpacing={0.6}>
                    {(node.city ?? node.country ?? "").toUpperCase()}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-paper-200/80 px-4 py-2.5 font-mono text-[9px] text-ink-400">
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full" style={{ background: "var(--color-flow-energy)" }} /> energy</span>
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full" style={{ background: "var(--color-flow-water)" }} /> water</span>
          <span className="flex items-center gap-1.5"><span className="h-1.5 w-4 rounded-full" style={{ background: "var(--color-flow-material)" }} /> material</span>
          <span>solid = confirmed · dashed = potential</span>
          <button
            type="button"
            onClick={() => {
              setSelected(null);
              setHovered(null);
            }}
            className="ml-auto text-ink-400 underline-offset-2 transition-colors hover:text-ink-700 hover:underline"
          >
            clear selection
          </button>
        </div>
      </div>

      <div className="space-y-4">
        <div className="panel px-4 py-4">
          <p className="label-mono text-[8.5px] text-ink-400">
            {selectedNode ? "Selected organisation" : "Network composition"}
          </p>
          {selectedNode ? (
            <>
              <h3 className="mt-1.5 text-[15px] font-semibold text-ink-900">{selectedNode.name}</h3>
              <p className="mt-0.5 text-[11px] text-ink-500">
                {sectorLabel(selectedNode.sector)} · {selectedNode.city ?? selectedNode.country}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {[
                  { label: "Streams", value: selectedNode.material_streams },
                  { label: "Open demands", value: selectedNode.open_demands },
                  { label: "Outbound lanes", value: selectedNode.outbound_links },
                  { label: "Inbound lanes", value: selectedNode.inbound_links },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-paper-200/80 bg-paper-50 px-2.5 py-2 transition-premium hover:bg-paper-100/70">
                    <p className="label-mono text-[8px] text-ink-400">{item.label}</p>
                    <p className="figure mt-1 text-[15px] text-ink-900">{item.value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3 space-y-1.5">
                {selectedFlows.length ? (
                  selectedFlows.map((edge) => {
                    const partnerId = edge.source === selectedNode.id ? edge.target : edge.source;
                    const partner = graph.nodes.find((node) => node.id === partnerId);
                    const outbound = edge.source === selectedNode.id;
                    const kind = flowKindForCategory(edge.category);
                    return (
                      <div key={edge.id} className="flex items-center justify-between gap-2 rounded-lg border border-paper-200/80 px-2.5 py-2">
                        <span className="min-w-0 truncate text-[11px] text-ink-600">
                          <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ background: flowColor(kind) }} />
                          {outbound ? "→ " : "← "}
                          {partner?.name ?? "Unknown"} · {flowLabel(kind)}
                        </span>
                        <Badge tone={edge.status === "confirmed" ? "lime" : "outline"} mono>
                          {edge.status}
                        </Badge>
                      </div>
                    );
                  })
                ) : (
                  <p className="text-[11px] text-ink-400">No modelled lanes for this node yet.</p>
                )}
              </div>
            </>
          ) : (
            <div className="mt-2 space-y-2.5 text-[11.5px] leading-relaxed text-ink-500">
              <p>Select a node to inspect its streams, intake requirements and modelled lanes. Hover to trace connected organisations and flow types.</p>
              <div className="rounded-lg border border-paper-200/80 bg-paper-50 px-3 py-2.5">
                <p className="font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">Confirmed lane</p>
                <p className="mt-1 text-[11px] text-ink-600">At least one verified recovery transaction with evidence is recorded on this lane.</p>
              </div>
              <div className="rounded-lg border border-paper-200/80 bg-paper-50 px-3 py-2.5">
                <p className="font-mono text-[9.5px] tracking-wide text-ink-400 uppercase">Potential lane</p>
                <p className="mt-1 text-[11px] text-ink-600">Produced by deterministic screening — a hypothesis, never a delivered transfer.</p>
              </div>
            </div>
          )}
        </div>

        <div className="panel px-4 py-4">
          <p className="label-mono text-[8.5px] text-ink-400">Lane register</p>
          <div className="mt-2 max-h-[280px] space-y-1.5 overflow-y-auto pr-1">
            {edges.map((edge) => {
              const source = graph.nodes.find((node) => node.id === edge.source);
              const target = graph.nodes.find((node) => node.id === edge.target);
              const quantity = edge.quantity_by_unit[0];
              const kind = flowKindForCategory(edge.category);
              return (
                <div key={edge.id} className="rounded-lg border border-paper-200/80 px-2.5 py-2 transition-premium hover:bg-paper-50">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[10.5px] text-ink-600">
                      {source?.name} → {target?.name}
                    </span>
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: flowColor(kind) }} />
                  </div>
                  <p className="mt-0.5 font-mono text-[9px] text-ink-400">
                    {titleCase(edge.category)} · {flowLabel(kind)} · {edge.opportunity_count} link{edge.opportunity_count === 1 ? "" : "s"}
                    {quantity ? ` · ${formatQuantity(quantity.quantity, quantity.unit)}` : ""}
                    {edge.status === "confirmed" ? " · verified" : ""}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
