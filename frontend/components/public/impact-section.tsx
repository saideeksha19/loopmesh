export function ImpactSection() {
  const states = [
    {
      title: "Identified opportunities",
      body: "Screened supply–demand pairs that meet deterministic rules, shown with evidence trails. A listing is a screening result, not a commitment.",
      tone: "neutral" as const,
    },
    {
      title: "Proposed or potential exchanges",
      body: "Work that has been recorded as a proposal or is still being evaluated before authorization steps are complete.",
      tone: "outline" as const,
    },
    {
      title: "Approved or active pipeline",
      body: "Proposals and transfers moving through governed steps such as review, approval, execution, or transport—tracked as pipeline, not yet verified recovery.",
      tone: "forest" as const,
    },
    {
      title: "Evidence-backed verified recovery",
      body: "Only transactions verified with required evidence contribute to recovered impact in the ledger; unverified stages remain separate from verified totals.",
      tone: "lime" as const,
    },
  ];

  const toneClass = {
    neutral: "border-paper-300 bg-white/60 text-ink-800",
    outline: "border-forest-600/50 bg-forest-900/30 text-forest-100",
    forest: "border-forest-500/60 bg-forest-800/40 text-paper-100",
    lime: "border-lime-400/40 bg-lime-400/10 text-lime-100",
  } as const;

  return (
    <section
      aria-labelledby="impact-heading"
      className="border-t border-forest-800/60 bg-[linear-gradient(180deg,#10291a_0%,#0f2418_100%)] px-5 py-24 sm:px-8 sm:py-28"
    >
      <div className="mx-auto max-w-[1440px]">
        <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">Impact philosophy</p>
        <h2
          id="impact-heading"
          className="mt-4 max-w-3xl text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-paper-50"
        >
          Circularity measured by evidence,
          <br />
          <span className="text-forest-200/90">not by intention.</span>
        </h2>
        <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
          LoopMesh separates discovery, authorization, movement, and verification so reported recovery reflects recorded proof—not hopeful projections.
        </p>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {states.map((s) => (
            <div key={s.title} className={`rounded-2xl border p-6 backdrop-blur-sm ${toneClass[s.tone]}`}>
              <p className="label-mono text-[9px] uppercase tracking-[0.16em] opacity-80">Lifecycle state</p>
              <h3 className="mt-3 text-[15px] font-semibold">{s.title}</h3>
              <p className="mt-3 text-[13px] leading-relaxed opacity-90">{s.body}</p>
            </div>
          ))}
        </div>

        <p className="mt-10 max-w-3xl text-[11.5px] leading-relaxed text-forest-300/90">
          Terminology aligns with the platform: opportunities are screening results; proposals and transactions move through governed steps; the impact ledger distinguishes verified recovered material from pipeline stages that are not yet counted as impact.
        </p>
      </div>
    </section>
  );
}
