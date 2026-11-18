type SectionConnectorProps = {
  /** Optional short label rendered beside the rail. */
  label?: string;
  tone?: "lime" | "teal" | "amber";
};

const tones = {
  lime: {
    line: "from-lime-400/0 via-lime-400/45 to-lime-400/0",
    dot: "border-lime-400/50 bg-lime-400/20 text-lime-200",
  },
  teal: {
    line: "from-teal-400/0 via-teal-400/45 to-teal-400/0",
    dot: "border-teal-400/50 bg-teal-400/20 text-teal-200",
  },
  amber: {
    line: "from-amber-400/0 via-amber-400/45 to-amber-400/0",
    dot: "border-amber-400/50 bg-amber-400/20 text-amber-200",
  },
} as const;

/**
 * The visual seam between two homepage sections: a fading rail with a small
 * travelling pulse, so consecutive sections read as one continuous story
 * instead of stacked blocks.
 */
export function SectionConnector({ label, tone = "lime" }: SectionConnectorProps) {
  const palette = tones[tone];

  return (
    <div aria-hidden="true" className="relative flex flex-col items-center bg-forest-950">
      <span className={`h-16 w-px bg-gradient-to-b ${palette.line} sm:h-20`} />
      <span className={`relative flex h-7 w-7 items-center justify-center rounded-full border ${palette.dot}`}>
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        <span className="absolute inset-0 animate-[node-pulse_5s_ease-in-out_infinite] rounded-full ring-1 ring-current/30" />
      </span>
      <span className={`h-16 w-px bg-gradient-to-b ${palette.line} sm:h-20`} />
      {label ? (
        <span className="label-mono absolute top-1/2 left-1/2 -translate-y-1/2 translate-x-6 text-[9px] tracking-[0.24em] text-forest-400/80">
          {label}
        </span>
      ) : null}
    </div>
  );
}
