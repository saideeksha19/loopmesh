const steps = [
  {
    step: "01",
    title: "List surplus",
    outcome: "Structured material profile",
    description:
      "Publish available materials, quantities, specifications, and handling constraints so surplus is described well enough for another operator to evaluate it.",
    accent: "from-lime-400/80 via-lime-400/25 to-transparent",
    badge: "border-lime-500/45 bg-lime-400/15 text-forest-800",
    icon: (
      <>
        <path d="M4 7h10" />
        <path d="M4 11h14" />
        <path d="M4 15h7" />
        <path d="M17 15h3" />
      </>
    ),
  },
  {
    step: "02",
    title: "Discover resources",
    outcome: "Ranked, evidence-backed matches",
    description:
      "LOOPMESH surfaces compatible receivers across sites, materials, and constraints, then ranks the opportunities with the context needed to compare them.",
    accent: "from-teal-400/80 via-teal-400/25 to-transparent",
    badge: "border-teal-500/45 bg-teal-500/12 text-teal-900",
    icon: (
      <>
        <circle cx="11" cy="11" r="6" />
        <path d="M20 20l-4.4-4.4" />
        <circle cx="11" cy="11" r="1.6" />
      </>
    ),
  },
  {
    step: "03",
    title: "Complete exchange",
    outcome: "Governed, verified transaction",
    description:
      "Move from proposal through review, approval, movement, and verification, with evidence recorded at each step so recovery claims stay traceable.",
    accent: "from-amber-400/80 via-amber-400/25 to-transparent",
    badge: "border-amber-500/45 bg-amber-400/15 text-amber-900",
    icon: (
      <>
        <path d="M5 12.5l4.5 4.5L19 7" />
        <path d="M5 6h5" />
      </>
    ),
  },
];

function StepLink({ last }: { last: boolean }) {
  if (last) return null;

  return (
    <div
      aria-hidden="true"
      className="relative flex h-14 w-full items-center justify-center lg:h-full lg:w-14 xl:w-20"
    >
      {/* Mobile / tablet: vertical rail with a downward chevron. */}
      <svg viewBox="0 0 2 56" preserveAspectRatio="none" className="h-14 w-1 lg:hidden">
        <line
          x1="1"
          y1="0"
          x2="1"
          y2="56"
          stroke="currentColor"
          strokeWidth="1.5"
          className="flow-dash text-forest-500/50"
        />
      </svg>
      <svg
        viewBox="0 0 10 7"
        className="absolute bottom-0 h-[7px] w-[10px] text-forest-500/80 lg:hidden"
        aria-hidden="true"
      >
        <path d="M0 0 L5 7 L10 0 Z" fill="currentColor" />
      </svg>

      {/* Desktop: horizontal rail with a right-pointing chevron. */}
      <svg viewBox="0 0 80 2" preserveAspectRatio="none" className="hidden h-1 w-full lg:block">
        <line
          x1="0"
          y1="1"
          x2="80"
          y2="1"
          stroke="currentColor"
          strokeWidth="1.5"
          className="flow-dash text-forest-500/50"
        />
      </svg>
      <svg
        viewBox="0 0 7 10"
        className="absolute right-0 hidden h-[10px] w-[7px] text-forest-500/80 lg:block"
        aria-hidden="true"
      >
        <path d="M0 0 L7 5 L0 10 Z" fill="currentColor" />
      </svg>
    </div>
  );
}

export function HowItWorksSection() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-heading"
      className="relative overflow-hidden border-t border-paper-300 bg-paper-50 px-5 py-24 sm:px-8 sm:py-28 lg:px-10"
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_60%_100%_at_50%_0%,rgba(198,243,92,0.16),transparent_70%)]"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-[1440px]">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-end lg:gap-14">
          <div>
            <p className="label-mono text-[10px] tracking-[0.22em] text-forest-600">How it works</p>
            <h2
              id="how-it-works-heading"
              className="mt-5 max-w-[22ch] text-[clamp(2.1rem,4.6vw,3.75rem)] font-semibold leading-[1.05] tracking-[-0.035em] text-ink-900"
            >
              How surplus becomes a{" "}
              <span className="relative inline-block">
                <span className="relative z-10">verified exchange.</span>
                <span
                  className="absolute inset-x-0 bottom-1 z-0 h-[0.32em] rounded-full bg-lime-400/45"
                  aria-hidden="true"
                />
              </span>
            </h2>
          </div>
          <p className="max-w-xl text-[14px] leading-relaxed text-ink-500 sm:text-[16px]">
            Three connected steps take a resource from an unstructured surplus note to a governed,
            evidence-backed exchange — with the same record carried the whole way through.
          </p>
        </div>

        <div className="mt-14 grid gap-0 lg:mt-16 lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:items-stretch">
          {steps.map((item, index) => (
            <div key={item.step} className="contents">
              <article className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-paper-300 bg-white p-7 shadow-[0_1px_0_rgba(16,41,26,0.04)] transition-[transform,box-shadow,border-color] duration-300 hover:-translate-y-1 hover:border-forest-400/45 hover:shadow-[0_24px_50px_-32px_rgba(16,41,26,0.45)] motion-reduce:hover:translate-y-0">
                <span
                  className={`absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r ${item.accent}`}
                  aria-hidden="true"
                />
                <div className="flex items-center gap-3">
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-xl border font-mono text-[11px] tracking-[0.08em] ${item.badge}`}
                  >
                    {item.step}
                  </span>
                  <span className="h-px flex-1 bg-paper-300/70" aria-hidden="true" />
                  <svg
                    viewBox="0 0 24 24"
                    className="h-5 w-5 text-forest-500 transition-colors group-hover:text-forest-700"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    {item.icon}
                  </svg>
                </div>

                <h3 className="mt-7 text-[17px] font-semibold uppercase tracking-[0.08em] text-ink-900">
                  {item.title}
                </h3>
                <p className="mt-3.5 text-[13.5px] leading-relaxed text-ink-500">{item.description}</p>

                <div className="mt-auto pt-7">
                  <p className="label-mono flex items-center gap-2 text-[9.5px] tracking-[0.16em] text-forest-500">
                    <span className="h-1 w-1 rounded-full bg-current" aria-hidden="true" />
                    {item.outcome}
                  </p>
                </div>
              </article>
              <StepLink last={index === steps.length - 1} />
            </div>
          ))}
        </div>

        <p className="mt-10 flex items-center gap-3 text-[11.5px] leading-relaxed text-ink-400">
          <span className="h-px w-10 bg-forest-500/40" aria-hidden="true" />
          Every step writes to the same auditable record — nothing is re-keyed between discovery and
          verification.
        </p>
      </div>
    </section>
  );
}
