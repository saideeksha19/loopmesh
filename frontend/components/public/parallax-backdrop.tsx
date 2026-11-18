"use client";

import { useEffect, useRef, type ReactNode } from "react";

type ParallaxBackdropProps = {
  children: ReactNode;
  /** Total travel in pixels across the viewport. Keep small for subtlety. */
  strength?: number;
  className?: string;
};

/**
 * Shifts a decorative layer slightly against scroll. One rAF-throttled,
 * passive scroll listener per section; skipped entirely when the visitor
 * prefers reduced motion. Purely presentational, so it is never in the
 * accessibility tree.
 */
export function ParallaxBackdrop({ children, strength = 28, className = "" }: ParallaxBackdropProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;

    const update = () => {
      frame = 0;
      const rect = node.getBoundingClientRect();
      const viewport = window.innerHeight || 1;
      // -1 (below the fold) → 1 (above the fold), clamped.
      const progress = (viewport / 2 - (rect.top + rect.height / 2)) / viewport;
      const clamped = Math.max(-1, Math.min(1, progress));
      node.style.setProperty("--parallax-y", `${(clamped * strength).toFixed(2)}px`);
    };

    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [strength]);

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={`parallax-layer pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      style={{ transform: "translate3d(0, var(--parallax-y, 0px), 0)" }}
    >
      {children}
    </div>
  );
}
