"use client";

import { useEffect, useState } from "react";

type HeroMediaProps = {
  /** Optional future video source (e.g. /videos/loopmesh-hero.mp4). When absent, shows atmospheric fallback. */
  videoSrc?: string;
  /** Optional poster image URL shown before playback or as fallback. */
  posterSrc?: string;
};

export function HeroMedia({ videoSrc, posterSrc }: HeroMediaProps) {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener?.("change", apply);
    return () => mq.removeEventListener?.("change", apply);
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden" aria-hidden="true">
      {videoSrc && !reducedMotion ? (
        <video
          className="h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          poster={posterSrc}
        >
          <source src={videoSrc} />
        </video>
      ) : (
        <div className="relative h-full w-full">
          {/* Atmospheric fallback: layered gradients and fog */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_20%,rgba(44,68,52,0.9)_0%,rgba(16,41,26,1)_45%,rgba(10,26,18,1)_100%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_50%_at_70%_60%,rgba(198,243,92,0.08)_0%,transparent_60%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_40%_at_20%_70%,rgba(95,138,112,0.12)_0%,transparent_55%)]" />
          {/* Subtle grid/texture hint */}
          <div className="absolute inset-0 opacity-[0.12] [background-image:linear-gradient(rgba(231,235,232,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(231,235,232,0.06)_1px,transparent_1px)] [background-size:48px_48px]" />
          {/* Soft moving haze (disabled in reduced motion) */}
          {!reducedMotion ? (
            <>
              <div className="absolute -left-[10%] top-[15%] h-[40vh] w-[50vw] rounded-full bg-lime-400/[0.06] blur-[80px] animate-[float-slow_18s_ease-in-out_infinite]" />
              <div className="absolute right-[-5%] bottom-[10%] h-[45vh] w-[55vw] rounded-full bg-forest-500/[0.18] blur-[90px] animate-[float-slow_22s_ease-in-out_infinite_reverse]" />
              <div className="absolute left-[30%] bottom-[20%] h-[30vh] w-[35vw] rounded-full bg-teal-500/[0.08] blur-[70px] animate-[float-slow_20s_ease-in-out_infinite]" />
            </>
          ) : (
            <>
              <div className="absolute -left-[10%] top-[15%] h-[40vh] w-[50vw] rounded-full bg-lime-400/[0.06] blur-[80px]" />
              <div className="absolute right-[-5%] bottom-[10%] h-[45vh] w-[55vw] rounded-full bg-forest-500/[0.18] blur-[90px]" />
            </>
          )}
          {/* Vignette */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_90%_90%_at_50%_40%,transparent_30%,rgba(10,26,18,0.55)_100%)]" />
        </div>
      )}
      {/* Overlays for readability */}
      <div className="absolute inset-0 bg-gradient-to-b from-forest-950/30 via-transparent to-forest-950/70" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_120%_80%_at_50%_0%,rgba(16,41,26,0.4)_0%,transparent_60%)]" />
    </div>
  );
}
