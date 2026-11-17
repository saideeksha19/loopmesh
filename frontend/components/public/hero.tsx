"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { HeroMedia } from "./hero-media";

export function Hero() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  const handleExplore = () => {
    const el = document.getElementById("explore");
    if (el) el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  };

  return (
    <section className="relative flex min-h-[100svh] items-center overflow-hidden bg-forest-950">
      <HeroMedia />
      <div className="relative z-10 mx-auto w-full max-w-[1440px] px-5 pb-24 pt-28 sm:px-8 sm:pt-32 lg:pt-36">
        <div className="max-w-3xl">
          <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/90 sm:text-[11px]">
            Industrial symbiosis · resource circularity
          </p>
          <h1 className="mt-5 text-[clamp(2.5rem,6vw,4.75rem)] font-semibold leading-[1.05] tracking-[-0.03em] text-paper-50">
            Transforming Waste
            <br />
            <span className="bg-gradient-to-r from-lime-300 via-lime-400 to-teal-300 bg-clip-text text-transparent">
              Into Opportunity.
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-forest-100/90 sm:text-[17px] sm:leading-relaxed">
            Connecting industries. Circulating resources. Creating value from what would otherwise go to waste.
          </p>

          {/* Subtle animated resource-flow details */}
          <div className="mt-8 flex flex-wrap items-center gap-3" aria-hidden="true">
            {[
              { label: "Energy", cls: "bg-lime-400/20 text-lime-200 border-lime-400/30" },
              { label: "Water", cls: "bg-teal-400/15 text-teal-100 border-teal-400/30" },
              { label: "Materials", cls: "bg-amber-400/15 text-amber-100 border-amber-400/30" },
            ].map((f) => (
              <span
                key={f.label}
                className={[
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em]",
                  f.cls,
                  reducedMotion ? "" : "animate-[pulse-soft_4s_ease-in-out_infinite]",
                ].join(" ")}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-90" />
                {f.label}
              </span>
            ))}
          </div>

          <div className="mt-10 flex flex-col gap-4 sm:flex-row sm:items-center">
            <Link
              href="/login"
              className="inline-flex h-12 items-center justify-center rounded-lg bg-lime-400 px-6 text-[13px] font-semibold tracking-wide text-forest-950 transition-colors hover:bg-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
            >
              Enter LoopMesh
            </Link>
            <button
              type="button"
              onClick={handleExplore}
              className="inline-flex h-12 items-center justify-center rounded-lg border border-forest-600/80 bg-forest-900/40 px-6 text-[13px] font-medium text-forest-100 backdrop-blur-sm transition-colors hover:border-lime-400/40 hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
            >
              Explore the ecosystem
            </button>
          </div>
        </div>
      </div>

      {/* Decorative flow line (subtle) */}
      {!reducedMotion ? (
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-10 h-24 opacity-60" aria-hidden="true">
          <svg viewBox="0 0 1440 96" className="h-full w-full" preserveAspectRatio="none">
            <defs>
              <linearGradient id="flowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(198,243,92,0)" />
                <stop offset="30%" stopColor="rgba(198,243,92,0.5)" />
                <stop offset="60%" stopColor="rgba(95,138,112,0.4)" />
                <stop offset="100%" stopColor="rgba(198,243,92,0)" />
              </linearGradient>
            </defs>
            <path
              d="M0,48 C240,80 480,16 720,48 C960,80 1200,16 1440,48"
              fill="none"
              stroke="url(#flowGrad)"
              strokeWidth="1.5"
              strokeDasharray="4 6"
              className="animate-[dash-flow_12s_linear_infinite]"
            />
          </svg>
        </div>
      ) : null}

      {/* Scroll hint */}
      <div className="absolute bottom-6 left-1/2 z-10 -translate-x-1/2" aria-hidden="true">
        <button
          type="button"
          onClick={handleExplore}
          className="flex flex-col items-center gap-1 text-forest-400/80 transition-colors hover:text-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded"
        >
          <span className="label-mono text-[9px] tracking-[0.2em]">Explore</span>
          <svg viewBox="0 0 24 24" className="h-4 w-4 animate-bounce" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14" />
            <path d="m19 12-7 7-7-7" />
          </svg>
        </button>
      </div>
    </section>
  );
}
