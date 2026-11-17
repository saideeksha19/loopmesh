import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  cinematic = false,
  children,
  className = "",
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  cinematic?: boolean;
  children?: ReactNode;
  className?: string;
}) {
  if (cinematic) {
    return (
      <section
        className={[
          "cinematic-surface panel-dark relative mb-7 overflow-hidden px-5 py-6 text-paper-50 sm:px-7 sm:py-7 lg:px-8",
          "animate-rise",
          className,
        ].join(" ")}
      >
        <div className="tech-grid-dark pointer-events-none absolute inset-0 opacity-35" aria-hidden />
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-lime-400/10 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -left-16 bottom-[-40px] h-64 w-64 rounded-full bg-teal-500/15 blur-3xl" aria-hidden />
        <div className="relative flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
          <div className="min-w-0 max-w-3xl">
            <p className="label-mono mb-2.5 inline-flex items-center gap-2 text-[9.5px] text-lime-300/90">
              <span className="h-1.5 w-1.5 rounded-full bg-lime-400 shadow-[0_0_10px_rgba(198,243,92,0.8)]" />
              {eyebrow}
            </p>
            <h1 className="text-[28px] leading-[1.08] font-semibold tracking-[-0.03em] text-paper-50 sm:text-[38px]">
              {title}
            </h1>
            {description ? (
              <p className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-paper-100/75">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        {children ? <div className="relative mt-5">{children}</div> : null}
      </section>
    );
  }

  return (
    <div className={["mb-7 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 animate-rise", className].join(" ")}>
      <div className="min-w-0 max-w-3xl">
        <p className="label-mono mb-2.5 text-[9.5px] text-forest-600">{eyebrow}</p>
        <h1 className="text-[26px] leading-[1.14] font-semibold tracking-[-0.025em] text-ink-900 sm:text-[34px]">
          {title}
        </h1>
        {description ? (
          <p className="mt-2.5 max-w-2xl text-[13px] leading-relaxed text-ink-500">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
