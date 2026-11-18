export function PlatformCapabilities() {
  const capabilities = [
    {
      title: "Material and resource intelligence",
      body: "Capture structured material profiles (category, quantity, condition, handling, availability) with intake through forms, CSV uploads, or specification documents—designed for consistent, reviewable records.",
    },
    {
      title: "Deterministic opportunity screening",
      body: "Screen supply–demand pairs against explicit engineering rules with a transparent evidence trail. Outcomes are rule-driven and reproducible; safety is not left to a model decision.",
    },
    {
      title: "Proposals with governed lifecycle",
      body: "Move from matched pair to recorded decisions through separate steps: submission, review, approval, execution, and verification—with authority separation enforced in the workflow.",
    },
    {
      title: "Evidence-gated transactions",
      body: "Recorded transfers are not treated as recovered material. Verified transactions require evidence (such as weighbridge documentation) and separation between who records and who verifies.",
    },
    {
      title: "Network visibility",
      body: "Explore an organization-level view of potential and confirmed flows across energy, water, and material lanes, with confirmed links tied to verified recovery activity.",
    },
    {
      title: "Auditability and impact accounting",
      body: "Append-only audit records document decisions and changes. The impact ledger separates pipeline stages from verified recovered totals so reported impact reflects evidence.",
    },
  ];

  return (
    <section
      id="platform"
      aria-labelledby="platform-heading"
      className="border-t border-paper-300 bg-paper-50 px-5 py-24 sm:px-8 sm:py-28"
    >
      <div className="mx-auto max-w-[1440px]">
        <p className="label-mono text-[10px] tracking-[0.22em] text-forest-600">Platform capabilities</p>
        <h2
          id="platform-heading"
          className="mt-4 max-w-3xl text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-ink-900"
        >
          Built for operational trust,
          <br />
          <span className="text-forest-700">not just discovery.</span>
        </h2>
        <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-ink-500 sm:text-[16px]">
          LoopMesh combines structured data, deterministic screening, and governed workflows so teams can move from insight to verified recovery with a clear record of decisions.
        </p>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {capabilities.map((c) => (
            <div
              key={c.title}
              className="rounded-2xl border border-paper-300 bg-white/70 p-6 shadow-[0_1px_0_rgba(16,41,26,0.04)] backdrop-blur-sm"
            >
              <h3 className="text-[15px] font-semibold text-ink-900">{c.title}</h3>
              <p className="mt-3 text-[13px] leading-relaxed text-ink-500">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
