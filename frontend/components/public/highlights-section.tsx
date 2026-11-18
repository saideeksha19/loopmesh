const highlights = [
  {
    title: "Material exchange",
    description:
      "Connect industrial producers and receivers through structured material profiles, so usable surplus can move to where it creates value instead of becoming waste.",
    accent: "from-lime-400/[0.12] to-transparent border-lime-400/20"
  },
  {
    title: "Resource discovery",
    description:
      "Explore the network to find compatible resources, sites, and demand signals across energy, water, and material streams with clear operational context.",
    accent: "from-teal-400/[0.10] to-transparent border-teal-400/20"
  },
  {
    title: "Opportunities",
    description:
      "Turn potential matches into actionable opportunities with screening, comparison, and governance-ready information that supports confident decisions.",
    accent: "from-amber-400/[0.09] to-transparent border-amber-400/20"
  },
  {
    title: "Transparent transactions",
    description:
      "Follow each exchange from proposal to execution and verification, maintaining traceability, approvals, and evidence throughout the transaction lifecycle.",
    accent: "from-paper-50/[0.06] to-transparent border-forest-500/45"
  },
];

export function HighlightsSection() {
  return (
    <section
      id="highlights"
      aria-labelledby="highlights-heading"
      className="relative overflow-hidden border-t border-forest-800/60 bg-[linear-gradient(180deg,#10291a_0%,#0f2418_100%)] px-5 py-24 sm:px-8 sm:py-28 lg:px-10"
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_15%_20%,rgba(198,243,92,0.08),transparent_35%),radial-gradient(circle_at_85%_70%,rgba(94,234,212,0.07),transparent_35%)]"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-[1440px]">
        <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">Highlights</p>
        <h2
          id="highlights-heading"
          className="mt-4 max-w-3xl text-[clamp(2rem,4.2vw,3.4rem)] font-semibold leading-[1.08] tracking-[-0.03em] text-paper-50"
        >
          Everything needed to run a trusted circular exchange.
        </h2>
        <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
          LOOPMESH brings discovery, decision-making, and execution together so businesses can
          collaborate on industrial resource recovery with clarity and confidence.
        </p>

        <div className="mt-14 grid gap-5 md:grid-cols-2">
          {highlights.map((item) => (
            <article
              key={item.title}
              className={`rounded-2xl border bg-gradient-to-br ${item.accent} p-6 backdrop-blur-sm sm:p-7`}
            >
              <h3 className="text-[18px] font-semibold tracking-[-0.01em] text-paper-50">
                {item.title}
              </h3>
              <p className="mt-3 max-w-xl text-[13.5px] leading-relaxed text-forest-100/85 sm:text-[14px]">
                {item.description}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
