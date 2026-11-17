"use client";

import { useEffect, useState } from "react";

const PROBLEMS = [
  {
    title: "Unused energy and heat",
    detail:
      "Thermal output, excess process heat, and recoverable energy often leave sites with no mapped destination.",
    accent: "lime",
  },
  {
    title: "Water discharge or underutilization",
    detail:
      "Treated or process water may be discharged, stored without purpose, or mismatched to nearby demand.",
    accent: "teal",
  },
  {
    title: "Discarded industrial by-products",
    detail:
      "Material streams with defined composition can become waste when potential receivers are not visible in time.",
    accent: "amber",
  },
] as const;

export function ProblemSection() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return (
    <section className="relative overflow-hidden border-t border-forest-800/80 bg-[linear-gradient(180deg,#0b1f15_0%,#10291a_40%,#1a2f22_100%)] px-5 py-24 sm:px-8 sm:py-28">
      <div className="pointer-events-none absolute inset-0 opacity-[0.35] [background-image:radial-gradient(circle_at_20%_20%,rgba(198,243,92,0.06),transparent_40%),radial-gradient(circle_at_80%_60%,rgba(95,138,112,0.08),transparent_45%)]" aria-hidden />
      <div className="relative mx-auto max-w-[1440px]">
        <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">The problem</p>
        <h2 className="mt-4 max-w-3xl text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-paper-50">
          Facilities operate in isolation.
          <br />
          <span className="text-forest-200/90">Valuable resources leave without a path.</span>
        </h2>
        <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
          Without shared visibility into material profiles, constraints, and nearby demand, recoverable flows remain disconnected across industrial sites.
        </p>

        <div className="mt-16 grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          {/* Isolated facility representations */}
          <div className="relative min-h-[320px] rounded-2xl border border-forest-700/60 bg-forest-950/50 p-6 backdrop-blur-sm sm:p-8">
            <div className="grid grid-cols-3 gap-4 sm:gap-6">
              {[
                { label: "Site A", x: "left" },
                { label: "Site B", x: "center" },
                { label: "Site C", x: "right" },
              ].map((site, i) => (
                <div key={site.label} className="flex flex-col items-center">
                  <div className="relative flex h-28 w-full max-w-[140px] flex-col items-center justify-end rounded-t-lg border border-forest-600/70 bg-gradient-to-b from-forest-800/80 to-forest-900/90 px-3 pb-4 sm:h-36">
                    <div className="absolute -top-3 left-1/2 h-6 w-6 -translate-x-1/2 rounded-full border border-forest-500/60 bg-forest-800/80" />
                    <div className="mb-2 h-8 w-8 rounded border border-forest-500/50 bg-forest-700/60" />
                    <div className="h-2 w-12 rounded-full bg-forest-600/80" />
                    <div className="mt-2 h-2 w-8 rounded-full bg-forest-600/60" />
                  </div>
                  <span className="mt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-forest-400">{site.label}</span>
                </div>
              ))}
            </div>
            {/* Disconnected dashed paths */}
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
              <path
                d="M 18% 70% L 18% 85% M 50% 70% L 50% 90% M 82% 70% L 82% 85%"
                fill="none"
                stroke="rgba(231,235,232,0.15)"
                strokeWidth="1.5"
                strokeDasharray="4 6"
              />
            </svg>
            {!reducedMotion ? (
              <div className="absolute bottom-4 left-6 right-6 flex justify-between text-[9px] font-mono uppercase tracking-wider text-forest-500/80">
                <span>no link</span>
                <span>no link</span>
                <span>no link</span>
              </div>
            ) : null}
          </div>

          {/* Problem cards */}
          <div className="space-y-4">
            {PROBLEMS.map((p) => (
              <div
                key={p.title}
                className="rounded-xl border border-forest-700/50 bg-forest-900/40 p-5 backdrop-blur-sm"
              >
                <div className="flex items-start gap-3">
                  <span
                    className={[
                      "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border",
                      p.accent === "lime" && "border-lime-400/30 bg-lime-400/10 text-lime-300",
                      p.accent === "teal" && "border-teal-400/30 bg-teal-400/10 text-teal-200",
                      p.accent === "amber" && "border-amber-400/30 bg-amber-400/10 text-amber-200",
                    ].join(" ")}
                  >
                    <span className="h-2 w-2 rounded-full bg-current" />
                  </span>
                  <div>
                    <h3 className="text-[14px] font-semibold text-paper-50">{p.title}</h3>
                    <p className="mt-2 text-[12.5px] leading-relaxed text-forest-100/75">{p.detail}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
