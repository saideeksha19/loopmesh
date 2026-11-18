"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

type RevealProps = {
  children: ReactNode;
  className?: string;
  /** Stagger in milliseconds, applied to the CSS transition only. */
  delay?: number;
  id?: string;
};

/**
 * Reveals its children once as they scroll into view. Uses a single
 * IntersectionObserver per instance and disconnects after the first paint, so
 * the cost after the animation is zero. Content stays visible when scripting
 * is unavailable or the visitor prefers reduced motion.
 */
export function Reveal({ children, className = "", delay = 0, id }: RevealProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (
      typeof IntersectionObserver === "undefined" ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          // `top < 0` also covers sections skipped by an instant scroll jump
          // (anchor links, restored scroll position), which would otherwise stay
          // hidden because they never intersect the viewport.
          if (!entry.isIntersecting && entry.boundingClientRect.top >= 0) continue;
          setVisible(true);
          observer.disconnect();
          break;
        }
      },
      // The very large top margin means anything already scrolled past counts
      // as intersecting, so an instant jump (anchor link or restored scroll)
      // can never leave a section stuck at opacity 0.
      { rootMargin: "9999px 0px -10% 0px", threshold: 0.08 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      id={id}
      className={["reveal", visible ? "reveal-visible" : "", className].filter(Boolean).join(" ")}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
