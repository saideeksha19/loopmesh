export function TrustGovernanceSection() {
  const items = [
    {
      title: "Governed proposals",
      body: "Changes move through explicit states: submission, review, approval, execution, and verification. Steps are recorded so decisions are not implicit.",
    },
    {
      title: "Approval authority separation",
      body: "Approvals require an evidence reference and an approver who did not submit the proposal, reducing self-authorization risk in the workflow.",
    },
    {
      title: "Evidence-gated verification",
      body: "Recorded transfers are not counted as recovered material until verification with required evidence occurs; the person who records a transfer is not the verifier.",
    },
    {
      title: "Auditability and traceable records",
      body: "Audit journal entries are written as part of the same operation that changes state, creating an append-only record of decisions and actions.",
    },
    {
      title: "Verified recovery, clearly separated",
      body: "The impact ledger distinguishes verified recovered totals from pipeline stages (proposed, accepted, in transit) that are not yet impact.",
    },
  ];

  return (
    <section
      aria-labelledby="trust-heading"
      className="border-t border-forest-800/60 bg-[linear-gradient(180deg,#0f2418_0%,#10291a_100%)] px-5 py-24 sm:px-8 sm:py-28"
    >
      <div className="mx-auto max-w-[1440px]">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.2fr] lg:items-start">
          <div>
            <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">Trust & governance</p>
            <h2
              id="trust-heading"
              className="mt-4 text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-paper-50"
            >
              Accountable exchanges,
              <br />
              <span className="text-teal-200/90">by design.</span>
            </h2>
            <p className="mt-6 max-w-xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
              Industrial symbiosis only works when participants can trust what changed, who approved it, and what evidence supports recovery claims.
            </p>
          </div>
          <div className="space-y-4">
            {items.map((item, idx) => (
              <div
                key={item.title}
                className="rounded-xl border border-forest-700/50 bg-forest-950/40 p-5 backdrop-blur-sm"
              >
                <div className="flex items-start gap-4">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-lime-400/30 bg-lime-400/10 font-mono text-[11px] text-lime-200">
                    {String(idx + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <h3 className="text-[14px] font-semibold text-paper-50">{item.title}</h3>
                    <p className="mt-2 text-[13px] leading-relaxed text-forest-100/75">{item.body}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
