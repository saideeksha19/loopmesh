"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

export function FinaleSection() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return (
    <section
      aria-labelledby="finale-heading"
      className="relative overflow-hidden border-t border-forest-800/80 bg-[radial-gradient(ellipse_80%_60%_at_50%_30%,#1a3a2a_0%,#10291a_40%,#081a10_100%)] px-5 py-28 sm:px-8 sm:py-36"
    >
      <div className="pointer-events-none absolute inset-0 opacity-50" aria-hidden>
        <div className="absolute left-[10%] top-[20%] h-[30vh] w-[40vw] rounded-full bg-lime-400/[0.06] blur-[100px]" />
        <div className="absolute right-[5%] bottom-[10%] h-[35vh] w-[45vw] rounded-full bg-teal-400/[0.05] blur-[100px]" />
      </div>
      <div className="relative mx-auto max-w-[1440px] text-center">
        <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">LoopMesh</p>
        <h2
          id="finale-heading"
          className="mx-auto mt-6 max-w-4xl text-[clamp(2.5rem,7vw,5rem)] font-semibold leading-[1.05] tracking-[-0.04em] text-paper-50"
        >
          Nothing wasted.
          <br />
          <span className="bg-gradient-to-r from-lime-300 via-teal-200 to-amber-200/90 bg-clip-text text-transparent">
            Everything connected.
          </span>
        </h2>
        <p className="mx-auto mt-8 max-w-2xl text-[15px] leading-relaxed text-forest-100/85 sm:text-[18px]">
          Transforming waste into opportunity through industrial symbiosis.
        </p>

        <div className="mx-auto mt-14 max-w-3xl">
          <svg viewBox="0 0 800 200" className="h-auto w-full" role="img" aria-label="Illustrative loop of connected resource flows">
            <defs>
              <linearGradient id="loopLime" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(198,243,92,0.2)" />
                <stop offset="50%" stopColor="rgba(198,243,92,0.85)" />
                <stop offset="100%" stopColor="rgba(198,243,92,0.2)" />
              </linearGradient>
              <linearGradient id="loopTeal" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(94,234,212,0.2)" />
                <stop offset="50%" stopColor="rgba(94,234,212,0.8)" />
                <stop offset="100%" stopColor="rgba(94,234,212,0.2)" />
              </linearGradient>
              <linearGradient id="loopAmber" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(251,191,36,0.2)" />
                <stop offset="50%" stopColor="rgba(251,191,36,0.75)" />
                <stop offset="100%" stopColor="rgba(251,191,36,0.2)" />
              </linearGradient>
            </defs>
            <path
              d="M 100 100 C 100 20, 300 20, 400 100 C 500 180, 700 180, 700 100 C 700 20, 500 20, 400 100 C 300 180, 100 180, 100 100"
              fill="none"
              stroke="url(#loopLime)"
              strokeWidth="2.5"
              strokeLinecap="round"
              className={reducedMotion ? "" : "animate-[dash-flow_10s_linear_infinite]"}
              strokeDasharray="8 10"
            />
            <path
              d="M 150 100 C 150 40, 320 40, 400 100 C 480 160, 650 160, 650 100"
              fill="none"
              stroke="url(#loopTeal)"
              strokeWidth="1.5"
              strokeLinecap="round"
              opacity="0.7"
              className={reducedMotion ? "" : "animate-[dash-flow_12s_linear_infinite]"}
              strokeDasharray="6 8"
            />
            <path
              d="M 180 100 C 180 60, 330 60, 400 100 C 470 140, 620 140, 620 100"
              fill="none"
              stroke="url(#loopAmber)"
              strokeWidth="1.5"
              strokeLinecap="round"
              opacity="0.6"
              className={reducedMotion ? "" : "animate-[dash-flow_14s_linear_infinite]"}
              strokeDasharray="5 7"
            />
          </svg>
        </div>

        <div className="mt-14">
          <Link
            href="/login"
            className="inline-flex h-14 items-center justify-center rounded-lg bg-lime-400 px-8 text-[14px] font-semibold tracking-wide text-forest-950 transition-colors hover:bg-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
          >
            Enter LoopMesh
          </Link>
        </div>
      </div>
    </section>
  );
}
