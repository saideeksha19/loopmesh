"use client";

import { useEffect, useState } from "react";

export function TransformationSection() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return (
    <section className="relative overflow-hidden border-t border-forest-800/60 bg-[linear-gradient(180deg,#1a2f22_0%,#10291a_50%,#0f2418_100%)] px-5 py-24 sm:px-8 sm:py-28">
      <div className="relative mx-auto max-w-[1440px]">
        <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">The transformation</p>
        <h2 className="mt-4 max-w-3xl text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-paper-50">
          From isolated sites
          <br />
          <span className="text-lime-300/90">to a connected resource ecosystem.</span>
        </h2>
        <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
          When facilities, material profiles, and compatibility signals align, disconnected streams become potential exchanges—turning what would be discarded into mapped opportunity.
        </p>

        <div className="mt-14 grid gap-8 lg:grid-cols-2 lg:items-center">
          <div className="rounded-2xl border border-forest-600/60 bg-forest-950/60 p-6 sm:p-8">
            <div className="flex items-center justify-between">
              <span className="label-mono text-[9px] text-forest-400">Network view (illustrative)</span>
              <span className="rounded-full border border-lime-400/30 bg-lime-400/10 px-2 py-0.5 font-mono text-[9px] text-lime-200">CONNECTED</span>
            </div>
            <div className="relative mt-6 aspect-[4/3] w-full">
              <svg viewBox="0 0 400 300" className="h-full w-full" role="img" aria-label="Illustrative connected facilities forming an ecosystem network">
                <defs>
                  <linearGradient id="lineEnergy" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="rgba(198,243,92,0.3)" />
                    <stop offset="100%" stopColor="rgba(198,243,92,0.9)" />
                  </linearGradient>
                  <linearGradient id="lineWater" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="rgba(94,234,212,0.3)" />
                    <stop offset="100%" stopColor="rgba(94,234,212,0.9)" />
                  </linearGradient>
                  <linearGradient id="lineMaterial" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="rgba(251,191,36,0.3)" />
                    <stop offset="100%" stopColor="rgba(251,191,36,0.9)" />
                  </linearGradient>
                </defs>
                {/* Connections */}
                <g className={reducedMotion ? "" : "opacity-100"}>
                  <path d="M 80 80 L 200 150" fill="none" stroke="url(#lineEnergy)" strokeWidth="2" strokeLinecap="round" className={reducedMotion ? "" : "animate-[dash-flow_8s_linear_infinite]"} strokeDasharray="6 8" />
                  <path d="M 320 80 L 200 150" fill="none" stroke="url(#lineWater)" strokeWidth="2" strokeLinecap="round" className={reducedMotion ? "" : "animate-[dash-flow_9s_linear_infinite]"} strokeDasharray="6 8" />
                  <path d="M 80 220 L 200 150" fill="none" stroke="url(#lineMaterial)" strokeWidth="2" strokeLinecap="round" className={reducedMotion ? "" : "animate-[dash-flow_10s_linear_infinite]"} strokeDasharray="6 8" />
                  <path d="M 320 220 L 200 150" fill="none" stroke="url(#lineEnergy)" strokeWidth="2" strokeLinecap="round" className={reducedMotion ? "" : "animate-[dash-flow_7s_linear_infinite]"} strokeDasharray="6 8" />
                </g>
                {/* Nodes */}
                <g>
                  <circle cx="80" cy="80" r="18" fill="#1e3529" stroke="rgba(198,243,92,0.6)" strokeWidth="2" />
                  <circle cx="320" cy="80" r="18" fill="#1e3529" stroke="rgba(94,234,212,0.6)" strokeWidth="2" />
                  <circle cx="80" cy="220" r="18" fill="#1e3529" stroke="rgba(251,191,36,0.6)" strokeWidth="2" />
                  <circle cx="320" cy="220" r="18" fill="#1e3529" stroke="rgba(198,243,92,0.5)" strokeWidth="2" />
                  <circle cx="200" cy="150" r="24" fill="#10291a" stroke="rgba(198,243,92,0.9)" strokeWidth="2.5" />
                </g>
                <g className="fill-forest-300 text-[8px] font-mono">
                  <text x="80" y="84" textAnchor="middle">A</text>
                  <text x="320" y="84" textAnchor="middle">B</text>
                  <text x="80" y="224" textAnchor="middle">C</text>
                  <text x="320" y="224" textAnchor="middle">D</text>
                  <text x="200" y="155" textAnchor="middle" className="fill-lime-200">Hub</text>
                </g>
              </svg>
            </div>
            <p className="mt-4 text-[11px] leading-relaxed text-forest-400">
              Illustrative network: facilities connected through potential resource flows (energy, water, materials). Real relationships appear in the workspace after data is added.
            </p>
          </div>

          <div className="space-y-6">
            <div className="rounded-xl border border-forest-700/50 bg-forest-900/30 p-6">
              <p className="label-mono text-[9px] text-forest-400">Before</p>
              <p className="mt-2 text-[15px] font-medium text-paper-100">Disconnected outputs</p>
              <p className="mt-2 text-[13px] leading-relaxed text-forest-100/75">
                Streams leave sites without visibility into who could use them, under what constraints, or with what evidence required.
              </p>
            </div>
            <div className="flex justify-center lg:justify-start" aria-hidden="true">
              <svg viewBox="0 0 24 24" className={`h-6 w-6 text-lime-400/80 ${reducedMotion ? "" : "animate-bounce"}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14" />
                <path d="m19 12-7 7-7-7" />
              </svg>
            </div>
            <div className="rounded-xl border border-lime-400/20 bg-lime-400/[0.06] p-6">
              <p className="label-mono text-[9px] text-lime-300/90">After</p>
              <p className="mt-2 text-[15px] font-medium text-paper-50">Mapped opportunities</p>
              <p className="mt-2 text-[13px] leading-relaxed text-forest-100/80">
                Profiles, rules, and workflows surface feasible exchanges so waste becomes an input for another operation—guided by evidence, not guesswork.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
