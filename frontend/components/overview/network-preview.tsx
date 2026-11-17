"use client";

import { useMemo, useState } from "react";

import { flowColor, flowKindForCategory, flowLabel } from "@/lib/flow";
import type { NetworkEdge, NetworkNode } from "@/lib/types";
import { formatNumber, formatQuantity, titleCase } from "@/lib/format";

const WIDTH = 760;
const HEIGHT = 420;
const CENTER_X = WIDTH / 2;
const CENTER_Y = HEIGHT / 2;

export function NetworkPreview({
  nodes,
  edges,
}: {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number; node: NetworkNode }>();
    const count = Math.max(nodes.length, 1);
    nodes.forEach((node, index) => {
      const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
      const radiusX = nodes.length <= 4 ? 220 : 265;
      const radiusY = nodes.length <= 4 ? 120 : 145;
      map.set(node.id, {
        x: CENTER_X + radiusX * Math.cos(angle),
        y: CENTER_Y + radiusY * Math.sin(angle),
        node,
      });
    });
    return map;
  }, [nodes]);

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

  const activeEdges = useMemo(() => {
    if (!activeId) return [];
    return edges.filter((e) => e.source === activeId || e.target === activeId);
  }, [activeId, edges]);

  const selectedNode = selected ? nodes.find((n) => n.id === selected) ?? null : null;
  const focusNode = activeId ? nodes.find((n) => n.id === activeId) ?? null : null;

  return (
    <div className="relative h-full w-full">
      <style>{`
        @keyframes lm-dash { to { stroke-dashoffset: -22; } }
        @keyframes lm-flow { 0% { offset-distance: 0%; opacity: 0; } 10% { opacity: .9; } 90% { opacity: .9; } 100% { offset-distance: 100%; opacity: 0; } }
      `}</style>
      <div className="tech-grid absolute inset-3 rounded-2xl opacity-60" aria-hidden />
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="relative h-[320px] w-full sm:h-[380px] lg:h-[420px]"
        role="img"
        aria-label="Interactive industrial resource network preview"
      >
        <defs>
          <filter id="lm-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* orbit rings */}
        <ellipse cx={CENTER_X} cy={CENTER_Y} rx={270} ry={155} fill="none" stroke="var(--color-paper-300)" strokeOpacity="0.35" strokeDasharray="2 8" />
        <ellipse cx={CENTER_X} cy={CENTER_Y} rx={170} ry={96} fill="none" stroke="var(--color-paper-300)" strokeOpacity="0.25" strokeDasharray="2 10" />

        {edges.map((edge) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const confirmed = edge.status === "confirmed";
          const kind = flowKindForCategory(edge.category);
          const color = flowColor(kind);
          const isActive = activeId === null || edge.source === activeId || edge.target === activeId;
          const midX = (source.x + target.x) / 2;
          const midY = (source.y + target.y) / 2;
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const len = Math.hypot(dx, dy) || 1;
          const curve = 18;
          const cx = midX - (dy / len) * curve;
          const cy = midY + (dx / len) * curve;
          const d = `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`;
          const baseOpacity = !isActive ? 0.08 : confirmed ? 0.9 : 0.28;
          return (
            <g key={edge.id}>
              <path
                d={d}
                fill="none"
                stroke={color}
                strokeWidth={confirmed ? 2.4 : 1.4}
                strokeOpacity={baseOpacity}
                strokeDasharray={confirmed ? undefined : "5 6"}
                style={
                  !confirmed && isActive
                    ? { animation: "lm-dash 2.4s linear infinite" }
                    : undefined
                }
              />
              {confirmed && isActive ? (
                <>
                  <path d={d} fill="none" stroke={color} strokeWidth={5} strokeOpacity={0.12} filter="url(#lm-glow)" />
                  <circle r={3} fill={color}>
                    <animateMotion dur="3.2s" repeatCount="indefinite" path={d} />
                  </circle>
                </>
              ) : null}
            </g>
          );
        })}

        {Array.from(positions.values()).map(({ x, y, node }) => {
          const isSupplier = node.material_streams > 0;
          const isConsumer = node.open_demands > 0;
          const links = node.inbound_links + node.outbound_links;
          const radius = 10 + Math.min(7, links * 1.6);
          const isActive = activeId === node.id;
          const isNeighbour = adjacent.has(node.id);
          const dimmed = activeId !== null && !isActive && !isNeighbour;
          const hasConfirmed = edges.some(
            (e) => e.status === "confirmed" && (e.source === node.id || e.target === node.id),
          );
          return (
            <g
              key={node.id}
              transform={`translate(${x} ${y})`}
              opacity={dimmed ? 0.28 : 1}
              className="cursor-pointer"
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => setSelected(node.id === selected ? null : node.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelected(node.id === selected ? null : node.id);
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={`${node.name}, ${node.material_streams} streams, ${node.open_demands} demands, ${links} lanes`}
            >
              <circle r={radius + 10} fill="var(--color-lime-400)" opacity={isActive ? 0.12 : 0} />
              {hasConfirmed ? <circle r={radius + 4} fill="none" stroke="var(--color-lime-400)" strokeOpacity={0.25} /> : null}
              <circle
                r={radius}
                fill={isSupplier ? "var(--color-forest-900)" : "var(--color-paper-50)"}
                stroke={isActive ? "var(--color-lime-400)" : hasConfirmed ? "var(--color-lime-500)" : isConsumer ? "var(--color-forest-600)" : "var(--color-paper-300)"}
                strokeWidth={isActive ? 2.5 : 1.6}
              />
              <circle r={2.4} fill={isSupplier ? "var(--color-lime-400)" : "var(--color-forest-600)"} opacity={isSupplier ? 1 : 0.6} />
              <text y={radius + 14} textAnchor="middle" className="pointer-events-none select-none" fill="var(--color-ink-700)" fontSize={11} fontWeight={isActive ? 600 : 500}>
                {node.name.length > 18 ? `${node.name.slice(0, 17)}…` : node.name}
              </text>
              <text y={radius + 26} textAnchor="middle" className="pointer-events-none select-none" fill="var(--color-ink-400)" fontSize={8.5} fontFamily="var(--font-mono)" letterSpacing={0.6}>
                {(node.city ?? node.country ?? "").toUpperCase()}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-2">
        <span className="rounded-full border border-paper-300/70 bg-paper-50/90 px-2.5 py-1 font-mono text-[9px] text-ink-500 backdrop-blur-sm">Energy · lime</span>
        <span className="rounded-full border border-paper-300/70 bg-paper-50/90 px-2.5 py-1 font-mono text-[9px] text-ink-500 backdrop-blur-sm">Water · teal-sage</span>
        <span className="rounded-full border border-paper-300/70 bg-paper-50/90 px-2.5 py-1 font-mono text-[9px] text-ink-500 backdrop-blur-sm">Materials · amber-lime</span>
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
        <div className="rounded-xl border border-paper-200/80 bg-paper-50/90 px-3 py-2.5 backdrop-blur-sm">
          {focusNode ? (
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="label-mono text-[8px] text-ink-400">{selectedNode ? "Selected node" : "Node focus"}</p>
                <p className="mt-0.5 text-[13px] font-semibold text-ink-900">{focusNode.name}</p>
                <p className="mt-0.5 font-mono text-[9.5px] text-ink-400">
                  {formatNumber(focusNode.material_streams)} streams · {formatNumber(focusNode.open_demands)} demands · {formatNumber(focusNode.inbound_links + focusNode.outbound_links)} lanes
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Array.from(new Set(activeEdges.map((e) => flowLabel(flowKindForCategory(e.category))))).map((label) => (
                  <span key={label} className="rounded-md border border-paper-300/70 bg-paper-100/70 px-2 py-0.5 font-mono text-[9px] text-ink-600">{label}</span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-[11.5px] leading-relaxed text-ink-500">
              Hover or select an organisation node to inspect its streams, demands and connected resource flows. Dashed lanes are modelled potential; animated confirmed lanes carry verified transactions.
            </p>
          )}
          {focusNode && activeEdges.length ? (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9.5px] text-ink-500">
              {activeEdges.slice(0, 3).map((edge) => {
                const q = edge.quantity_by_unit[0];
                const otherId = edge.source === focusNode.id ? edge.target : edge.source;
                const other = nodes.find((n) => n.id === otherId);
                return (
                  <span key={edge.id} className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: flowColor(flowKindForCategory(edge.category)) }} />
                    {titleCase(edge.category)} {edge.source === focusNode.id ? "→" : "←"} {other?.name ?? "node"}
                    {q ? ` · ${formatQuantity(q.quantity, q.unit)}` : ""}
                    {edge.status === "confirmed" ? " · verified" : ""}
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
        {selectedNode ? (
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="rounded-xl border border-paper-300/70 bg-paper-50 px-3 py-2 font-mono text-[9.5px] text-ink-500 transition-premium hover:bg-paper-100"
          >
            Clear selection
          </button>
        ) : null}
      </div>
    </div>
  );
}
