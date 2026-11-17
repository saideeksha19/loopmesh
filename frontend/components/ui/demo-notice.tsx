import { InfoIcon } from "@/components/icons";

export function DemoNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={[
        "flex items-start gap-2.5 rounded-xl border border-paper-300 bg-paper-50 text-ink-500",
        compact ? "px-3 py-2" : "px-4 py-3",
      ].join(" ")}
    >
      <InfoIcon className="mt-[1px] h-4 w-4 shrink-0 text-ink-400" />
      <p className={compact ? "text-[11px] leading-relaxed" : "text-[11.5px] leading-relaxed"}>
        <span className="font-mono text-[10px] tracking-wider text-ink-700 uppercase">
          Demo dataset
        </span>{" "}
        — organisations, material streams, proposals and transactions are synthetic. No real
        partnership, delivery or environmental saving is claimed.
      </p>
    </div>
  );
}
