"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      setReduced(false);
      return;
    }
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", update);
      return () => mq.removeEventListener("change", update);
    }
    mq.addListener(update);
    return () => mq.removeListener(update);
  }, []);
  return reduced;
}

function parseMetric(value: string): { prefix: string; number: number; decimals: number; suffix: string } | null {
  const match = value.trim().match(/^([^0-9-+]*)([+-]?\d[\d,]*(?:\.\d+)?)([\s\S]*)$/);
  if (!match) return null;
  const raw = match[2].replace(/,/g, "");
  const number = Number(raw);
  if (!Number.isFinite(number)) return null;
  const decimals = raw.includes(".") ? (raw.split(".")[1]?.length ?? 0) : 0;
  return { prefix: match[1], number, decimals, suffix: match[3] };
}

function formatLike(number: number, decimals: number): string {
  return new Intl.NumberFormat("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(number);
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export function StatCard({
  label,
  value,
  unit,
  meta,
  icon,
  accent = false,
  delay = 0,
}: {
  label: string;
  value: string;
  unit?: string;
  meta?: string;
  icon?: ReactNode;
  accent?: boolean;
  delay?: number;
}) {
  const parsed = parseMetric(value);
  const reducedMotion = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    setDisplay(value);
    if (!parsed || reducedMotion) return;
    const start = performance.now() + delay;
    const duration = 900;
    const from = 0;
    const to = parsed.number;

    const tick = (now: number) => {
      if (now < start) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const t = Math.min(1, (now - start) / duration);
      const current = from + (to - from) * easeOutCubic(t);
      setDisplay(`${parsed.prefix}${formatLike(current, parsed.decimals)}${parsed.suffix}`);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        setDisplay(value);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, delay, reducedMotion, parsed?.number, parsed?.decimals, parsed?.prefix, parsed?.suffix]);

  return (
    <div
      className={[
        "panel group relative overflow-hidden p-4 transition-premium",
        accent ? "bg-gradient-to-br from-paper-50 to-lime-400/[0.06]" : "",
      ].join(" ")}
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="pointer-events-none absolute -right-8 -top-8 h-20 w-20 rounded-full bg-lime-400/10 opacity-0 blur-xl transition-opacity duration-300 group-hover:opacity-100" aria-hidden />
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label-mono text-[9px] text-ink-400">{label}</p>
          <div className="mt-2.5 flex items-end gap-1.5">
            <p className="figure text-[28px] leading-none tracking-[-0.03em] text-ink-900 sm:text-[30px]">
              {display}
            </p>
            {unit ? <span className="mb-0.5 text-[11px] text-ink-400">{unit}</span> : null}
          </div>
        </div>
        {icon ? (
          <span
            className={[
              "flex h-8 w-8 items-center justify-center rounded-xl border shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]",
              accent
                ? "border-lime-500/30 bg-lime-400/20 text-forest-800"
                : "border-paper-300/80 bg-paper-100/80 text-ink-500",
            ].join(" ")}
          >
            {icon}
          </span>
        ) : null}
      </div>
      {meta ? <p className="mt-2.5 border-t border-paper-200/80 pt-2.5 text-[10.5px] leading-relaxed text-ink-400">{meta}</p> : null}
    </div>
  );
}
