"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { HeroMedia } from "./hero-media";

const chain = [
  {
    step: "01",
    title: "Surplus listed",
    meta: "Material profile complete",
    tone: "border-lime-400/70 text-lime-300",
    dot: "bg-lime-400",
  },
  {
    step: "02",
    title: "Receiver matched",
    meta: "Compatible sites surfaced",
    tone: "border-teal-400/70 text-teal-300",
    dot: "bg-teal-400",
  },
  {
    step: "03",
    title: "Exchange verified",
    meta: "Evidence recorded",
    tone: "border-amber-400/70 text-amber-300",
    dot: "bg-amber-400",
  },
];

export function Hero() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  const scrollToExplore = () => {
    const el = document.getElementById("explore");
    if (el) el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  };

  return (
    <section className="relative isolate overflow-hidden bg-forest-950">
      <HeroMedia />
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_65%_50%_at_38%_10%,rgba(198,243,92,0.13),transparent_62%)]"
        aria-hidden="true"
      />

      <div className="relative z-10 mx-auto w-full max-w-[1440px] px-5 pt-32 pb-20 sm:px-8 sm:pt-36 sm:pb-24 lg:px-10 lg:pt-40 lg:pb-28">
        <div className="grid items-center gap-14 lg:grid-cols-[1.08fr_0.92fr] lg:gap-16">
          <div className="max-w-[46rem]">
            <p className="label-mono inline-flex items-center gap-2.5 rounded-full border border-lime-400/25 bg-forest-900/40 px-3.5 py-1.5 text-[10px] tracking-[0.2em] text-lime-200/95 backdrop-blur-sm sm:text-[11px]">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-lime-400/70 motion-safe:animate-[node-pulse_4s_ease-in-out_infinite]" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-lime-400" />
              </span>
              Industrial circular economy platform
            </p>

            <h1 className="mt-8 text-balance text-[clamp(2.6rem,5.4vw,5rem)] font-semibold leading-[1.02] tracking-[-0.04em] text-paper-50">
              One Industry&rsquo;s Waste.{" "}
              <span className="bg-gradient-to-r from-lime-300 via-lime-200 to-teal-200 bg-clip-text text-transparent">
                Another Industry&rsquo;s Resource.
              </span>
            </h1>

            <p className="mt-8 max-w-xl text-[clamp(1.05rem,1.7vw,1.35rem)] font-medium leading-[1.5] tracking-[-0.01em] text-lime-100/95">
              A clear path from surplus to verified value.
            </p>
            <p className="mt-4 max-w-xl text-[14.5px] leading-relaxed text-forest-100/80 sm:text-[15.5px]">
              Connect businesses, exchange materials, and build a more circular industrial economy —
              with one governed record from listing to verification.
            </p>

            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
              <button
                type="button"
                onClick={scrollToExplore}
                className="group inline-flex h-13 min-h-12 items-center justify-center gap-2 rounded-xl bg-lime-400 px-7 text-[13px] font-semibold tracking-wide text-forest-950 shadow-[0_0_0_1px_rgba(198,243,92,0.35),0_22px_45px_-22px_rgba(198,243,92,0.6)] transition-colors hover:bg-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-300 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
              >
                Explore the Network
                <svg
                  viewBox="0 0 24 24"
                  className="h-4 w-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M5 12h13" />
                  <path d="m12 5 7 7-7 7" />
                </svg>
              </button>
              <Link
                href="/login"
                className="inline-flex h-13 min-h-12 items-center justify-center rounded-xl border border-lime-400/35 bg-lime-400/10 px-7 text-[13px] font-semibold tracking-wide text-lime-100 backdrop-blur-sm transition-colors hover:border-lime-300/60 hover:bg-lime-400/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
              >
                Get Started
              </Link>
            </div>

            <p className="mt-6 text-[12.5px] text-forest-300/85">
              Already part of a network?{" "}
              <Link
                href="/login"
                className="rounded-sm font-medium text-paper-100 underline decoration-lime-400/40 decoration-1 underline-offset-4 transition-colors hover:text-lime-200 hover:decoration-lime-300"
              >
                Sign in
              </Link>
            </p>
          </div>

          {/* Compact preview of the three-step exchange lifecycle */}
          <div className="relative mx-auto w-full max-w-md lg:mx-0 lg:max-w-none">
            <div className="relative overflow-hidden rounded-3xl border border-forest-700/60 bg-gradient-to-b from-forest-900/70 via-forest-900/50 to-forest-950/80 p-6 shadow-[0_36px_90px_-46px_rgba(0,0,0,0.85)] backdrop-blur-sm sm:p-8">
              <div
                className="pointer-events-none absolute inset-0 opacity-60 [background-image:radial-gradient(circle_at_85%_0%,rgba(198,243,92,0.14),transparent_45%),radial-gradient(circle_at_0%_100%,rgba(94,234,212,0.1),transparent_45%)]"
                aria-hidden="true"
              />
              <div className="relative">
                <p className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-forest-300">
                  Exchange lifecycle
                </p>

                <div className="relative mt-6 pl-10">
                  <span
                    className="absolute left-[15px] top-2 bottom-2 w-px bg-gradient-to-b from-lime-400/50 via-teal-400/40 to-amber-400/35"
                    aria-hidden="true"
                  />
                  <span
                    className="absolute left-[11px] top-2 bottom-2 w-[9px] bg-[repeating-linear-gradient(to_bottom,rgba(246,247,244,0.55)_0_4px,transparent_4px_12px)] motion-safe:animate-[dash-flow_6s_linear_infinite]"
                    aria-hidden="true"
                  />

                  <ul className="space-y-7">
                    {chain.map((item) => (
                      <li key={item.step} className="relative">
                        <span
                          className={`absolute -left-10 top-1 flex h-[26px] w-[26px] items-center justify-center rounded-full border bg-forest-950 font-mono text-[9px] ${item.tone}`}
                          aria-hidden="true"
                        >
                          {item.step}
                        </span>
                        <p className="flex items-center gap-2 text-[14px] font-semibold text-paper-50">
                          <span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} aria-hidden="true" />
                          {item.title}
                        </p>
                        <p className="mt-1.5 text-[12px] leading-relaxed text-forest-200/75">
                          {item.meta}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="mt-7 flex items-center justify-between gap-3 border-t border-forest-700/55 pt-5">
                  <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-forest-400">
                    Illustrative workflow
                  </p>
                  <a
                    href="#how-it-works"
                    className="rounded-sm text-[11.5px] font-medium text-lime-200/90 transition-colors hover:text-lime-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
                  >
                    See the three steps →
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
