import { ParallaxBackdrop } from "./parallax-backdrop";

type NetworkNode = {
  label: string;
  /** Node centre as a percentage of the square canvas. */
  node: [number, number];
  /** Label centre, pushed further out so pills clear the orbit rings. */
  labelPos: [number, number];
  tone: string;
  glow: string;
};

// Node ring radius 232/800, label ring radius ~286/800.
const outerNodes: NetworkNode[] = [
  { label: "Steel & metals", node: [50, 21], labelPos: [50, 14.25], tone: "#c6f35c", glow: "rgba(198,243,92,0.22)" },
  { label: "Chemicals", node: [70.5, 29.5], labelPos: [75.3, 24.7], tone: "#5eead4", glow: "rgba(94,234,212,0.2)" },
  { label: "Energy", node: [79, 50], labelPos: [85.75, 50], tone: "#fbbf24", glow: "rgba(251,191,36,0.2)" },
  { label: "Manufacturing", node: [70.5, 70.5], labelPos: [75.3, 75.3], tone: "#c6f35c", glow: "rgba(198,243,92,0.2)" },
  { label: "Construction", node: [50, 79], labelPos: [50, 85.75], tone: "#d9f78a", glow: "rgba(217,247,138,0.18)" },
  { label: "Agriculture", node: [29.5, 70.5], labelPos: [24.7, 75.3], tone: "#fbbf24", glow: "rgba(251,191,36,0.16)" },
  { label: "Water utilities", node: [21, 50], labelPos: [14.25, 50], tone: "#5eead4", glow: "rgba(94,234,212,0.2)" },
  { label: "Logistics", node: [29.5, 29.5], labelPos: [24.7, 24.7], tone: "#e7ebe8", glow: "rgba(231,235,232,0.16)" },
];

const legends = [
  { value: "8", label: "Industries", body: "Producers, processors and receivers across heavy industry." },
  { value: "12+", label: "Material streams", body: "Metals, solvents, water, heat, packaging and by-products." },
  { value: "1", label: "Shared record", body: "One auditable record from surplus listing to verified recovery." },
];

/**
 * Circular-economy network: a decorative map of how industries and material
 * streams connect through the platform. All geometry is SVG plus CSS
 * keyframes, so it costs no JavaScript beyond the parallax layer and stops
 * moving under prefers-reduced-motion.
 */
export function NetworkSection() {
  return (
    <section
      id="network"
      aria-labelledby="network-heading"
      className="relative overflow-hidden border-t border-forest-800/60 bg-[radial-gradient(ellipse_90%_70%_at_50%_10%,#143223_0%,#0d2317_55%,#081a10_100%)] px-5 py-24 sm:px-8 sm:py-28 lg:px-10"
    >
      <ParallaxBackdrop strength={34}>
        <div className="absolute left-1/2 top-[18%] h-[42vh] w-[70vw] max-w-[900px] -translate-x-1/2 rounded-full bg-lime-400/[0.05] blur-[120px]" />
        <div className="absolute -right-[10%] bottom-[8%] h-[38vh] w-[38vw] rounded-full bg-teal-400/[0.05] blur-[110px]" />
      </ParallaxBackdrop>

      <div className="relative mx-auto max-w-[1440px]">
        <div className="mx-auto max-w-3xl text-center">
          <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">
            Circular economy network
          </p>
          <h2
            id="network-heading"
            className="mt-4 text-balance text-[clamp(2rem,4.6vw,3.6rem)] font-semibold leading-[1.06] tracking-[-0.035em] text-paper-50"
          >
            Every output is an input{" "}
            <span className="bg-gradient-to-r from-lime-300 via-teal-200 to-amber-200 bg-clip-text text-transparent">
              somewhere else.
            </span>
          </h2>
          <p className="mx-auto mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
            Industries rarely sit in a straight line. LOOPMESH maps surplus, demand, and handling
            constraints across sectors so material streams can close into loops instead of ending as
            waste.
          </p>
        </div>

        <div className="relative mx-auto mt-10 w-full max-w-[600px] sm:mt-12 lg:max-w-[760px]">
          <div className="relative aspect-square w-full">
            <svg
              viewBox="0 0 800 800"
              className="h-full w-full"
              role="img"
              aria-label="Illustrative circular network connecting eight industries through a central exchange hub"
            >
              <defs>
                <radialGradient id="networkHub" cx="50%" cy="42%" r="62%">
                  <stop offset="0%" stopColor="rgba(198,243,92,0.3)" />
                  <stop offset="60%" stopColor="rgba(198,243,92,0.08)" />
                  <stop offset="100%" stopColor="rgba(198,243,92,0.02)" />
                </radialGradient>
                <linearGradient id="networkSpoke" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="rgba(198,243,92,0.45)" />
                  <stop offset="100%" stopColor="rgba(198,243,92,0.06)" />
                </linearGradient>
                <linearGradient id="networkArcA" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="rgba(198,243,92,0.05)" />
                  <stop offset="50%" stopColor="rgba(198,243,92,0.6)" />
                  <stop offset="100%" stopColor="rgba(94,234,212,0.15)" />
                </linearGradient>
                <linearGradient id="networkArcB" x1="100%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="rgba(94,234,212,0.08)" />
                  <stop offset="50%" stopColor="rgba(94,234,212,0.5)" />
                  <stop offset="100%" stopColor="rgba(251,191,36,0.18)" />
                </linearGradient>
                <marker
                  id="networkArrow"
                  viewBox="0 0 10 10"
                  refX="7"
                  refY="5"                    markerWidth="6"
                    markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(198,243,92,0.9)" />
                </marker>
              </defs>

              {/* Orbit rings */}
              <circle cx="400" cy="400" r="322" fill="none" stroke="rgba(231,235,232,0.07)" strokeWidth="1" />
              <g className="orbit-ring">
                <circle
                  cx="400"
                  cy="400"
                  r="322"
                  fill="none"
                  stroke="rgba(198,243,92,0.22)"
                  strokeWidth="1.4"
                  strokeDasharray="2 16"
                  strokeLinecap="round"
                />
              </g>
              <circle
                cx="400"
                cy="400"
                r="232"
                fill="none"
                stroke="rgba(231,235,232,0.12)"
                strokeWidth="1"
                strokeDasharray="3 9"
              />
              <circle cx="400" cy="400" r="128" fill="none" stroke="rgba(231,235,232,0.09)" strokeWidth="1" />

              {/* Spokes from the hub to each industry node */}
              {outerNodes.map((node) => (
                <line
                  key={`spoke-${node.label}`}
                  x1="400"
                  y1="400"
                  x2={(node.node[0] / 100) * 800}
                  y2={(node.node[1] / 100) * 800}
                  stroke="url(#networkSpoke)"
                  strokeWidth="1.2"
                />
              ))}

              {/* Cross-sector loop arcs: metal recovery and chemical reuse */}
              <path
                d="M 400 168 C 508 214, 594 318, 564 564"
                fill="none"
                stroke="url(#networkArcA)"
                strokeWidth="2.6"
                strokeLinecap="round"
                markerEnd="url(#networkArrow)"
                className="flow-dash-slow"
              />
              <path
                d="M 564 236 C 436 330, 330 434, 236 564"
                fill="none"
                stroke="url(#networkArcB)"
                strokeWidth="2.2"
                strokeLinecap="round"
                markerEnd="url(#networkArrow)"
                className="flow-dash-slow"
              />

              {/* Hub */}
              <circle cx="400" cy="400" r="108" fill="url(#networkHub)" />
              <circle cx="400" cy="400" r="72" fill="none" stroke="rgba(198,243,92,0.45)" strokeWidth="1.4" />
              <circle
                cx="400"
                cy="400"
                r="56"
                fill="rgba(11,31,21,0.85)"
                stroke="rgba(198,243,92,0.55)"
                strokeWidth="1"
              />
              <circle
                cx="400"
                cy="400"
                r="88"
                fill="none"
                stroke="rgba(198,243,92,0.18)"
                strokeWidth="1"
                strokeDasharray="4 10"
                className="flow-dash-slow"
              />

              {/* Industry nodes */}
              {outerNodes.map((node, index) => {
                const x = (node.node[0] / 100) * 800;
                const y = (node.node[1] / 100) * 800;
                return (
                  <g key={`node-${node.label}`}>
                    <circle cx={x} cy={y} r="18" fill={node.glow} />
                    <circle
                      cx={x}
                      cy={y}
                      r="7"
                      fill="#0b1f15"
                      stroke={node.tone}
                      strokeWidth="2.2"
                      className="node-pulse"
                      style={{ animationDelay: `${index * 420}ms` }}
                    />
                  </g>
                );
              })}

              {/* Inner material-stream nodes */}
              {[
                [490.5, 490.5],
                [309.5, 490.5],
                [309.5, 309.5],
                [490.5, 309.5],
              ].map(([x, y], index) => (
                <circle
                  key={`inner-${index}`}
                  cx={x}
                  cy={y}
                  r="5"
                  fill="rgba(214,236,220,0.55)"
                  stroke="rgba(11,31,21,0.9)"
                  strokeWidth="1.5"
                />
              ))}
            </svg>

            {/* Hub label */}
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="label-mono text-[9px] tracking-[0.2em] text-paper-50 sm:text-[10px]">
                LOOPMESH
              </span>
              <span className="mt-1 font-mono text-[7.5px] uppercase tracking-[0.16em] text-lime-200/80 sm:text-[8.5px]">
                Exchange hub
              </span>
            </div>

            {/* Industry labels — hidden on small screens where they would collide */}
            {outerNodes.map((node) => (
              <div
                key={`label-${node.label}`}
                className="pointer-events-none absolute hidden -translate-x-1/2 -translate-y-1/2 md:block"
                style={{ left: `${node.labelPos[0]}%`, top: `${node.labelPos[1]}%` }}
              >
                <span className="label-mono flex items-center gap-1.5 whitespace-nowrap rounded-full border border-forest-700/60 bg-forest-950/80 px-2.5 py-1 text-[9px] tracking-[0.14em] text-paper-100 backdrop-blur-sm">
                  <span
                    className="h-1 w-1 rounded-full"
                    style={{ backgroundColor: node.tone }}
                    aria-hidden="true"
                  />
                  {node.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Mobile legend replaces the absolutely positioned labels */}
        <div className="mx-auto mt-8 flex max-w-xl flex-wrap justify-center gap-2 md:hidden">
          {outerNodes.map((node) => (
            <span
              key={`chip-${node.label}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-forest-700/70 bg-forest-950/60 px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-[0.12em] text-forest-100/85"
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: node.tone }}
                aria-hidden="true"
              />
              {node.label}
            </span>
          ))}
        </div>

        <div className="mx-auto mt-14 grid max-w-4xl gap-3 sm:grid-cols-3">
          {legends.map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-forest-700/55 bg-forest-950/45 p-5 backdrop-blur-sm"
            >
              <p className="font-mono text-[22px] leading-none text-lime-200">{item.value}</p>
              <p className="label-mono mt-3 text-[9.5px] tracking-[0.18em] text-paper-100">
                {item.label}
              </p>
              <p className="mt-2 text-[12px] leading-relaxed text-forest-200/75">{item.body}</p>
            </div>
          ))}
        </div>

        <p className="mx-auto mt-8 max-w-2xl text-center text-[11.5px] leading-relaxed text-forest-300/75">
          Network illustration for demonstration only; it does not represent live operational data.
        </p>
      </div>
    </section>
  );
}
