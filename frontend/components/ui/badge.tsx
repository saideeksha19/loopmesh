import type { ReactNode } from "react";

export type BadgeTone =
  | "neutral"
  | "forest"
  | "lime"
  | "outline"
  | "warning"
  | "danger"
  | "muted";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-paper-300 bg-paper-200/60 text-ink-700",
  forest: "border-forest-700/25 bg-forest-800/[0.08] text-forest-700",
  lime: "border-lime-500/40 bg-lime-400/20 text-forest-800",
  outline: "border-paper-300 bg-transparent text-ink-500",
  warning: "border-clay-500/30 bg-clay-500/10 text-clay-500",
  danger: "border-rust-500/30 bg-rust-500/10 text-rust-500",
  muted: "border-transparent bg-paper-200/70 text-ink-400",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
  mono = false,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  mono?: boolean;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded border px-1.5 py-[2px] text-[10px] leading-4",
        mono ? "font-mono uppercase tracking-wider" : "font-medium",
        TONES[tone],
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}

export function CompatibilityBadge({ status }: { status: string }) {
  const map: Record<string, { tone: BadgeTone; label: string }> = {
    compatible: { tone: "lime", label: "Compatible" },
    conditional: { tone: "warning", label: "Conditional" },
    incompatible: { tone: "danger", label: "Incompatible" },
    unverified: { tone: "outline", label: "Unverified" },
  };
  const entry = map[status] ?? { tone: "neutral" as BadgeTone, label: status };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

export function RuleStatusDot({ status }: { status: string }) {
  const map: Record<string, string> = {
    pass: "bg-forest-600",
    warning: "bg-clay-500",
    fail: "bg-rust-500",
    unknown: "bg-ink-300",
  };
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${map[status] ?? "bg-ink-300"}`} />;
}
