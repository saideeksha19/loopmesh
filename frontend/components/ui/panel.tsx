import type { ReactNode } from "react";

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`panel animate-rise ${className}`}>{children}</section>;
}

export function PanelHeader({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-paper-200/80 px-5 py-4 sm:px-6">
      <div className="min-w-0">
        {eyebrow ? <p className="label-mono mb-1.5 text-[8.5px] text-ink-400">{eyebrow}</p> : null}
        <h2 className="text-[15px] font-semibold tracking-[-0.015em] text-ink-900">{title}</h2>
        {subtitle ? (
          <p className="mt-1 max-w-xl text-[12px] leading-relaxed text-ink-500">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
