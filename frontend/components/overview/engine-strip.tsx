const STAGES = [
  {
    step: "01",
    title: "Structured input",
    body: "Forms, CSV files and specification documents become measured material profiles, demands and handling constraints.",
  },
  {
    step: "02",
    title: "Deterministic screening",
    body: "Nine engineering rules test category, hazard, purity, contamination, quantity, distance, timing and condition.",
  },
  {
    step: "03",
    title: "Evidenced recovery",
    body: "Proposals move through accepted, transported and verified states. Only verified mass enters the impact ledger.",
  },
];

export function EngineStrip() {
  return (
    <div className="panel overflow-hidden">
      <div className="grid divide-y divide-paper-200/80 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {STAGES.map((stage, idx) => (
          <div key={stage.step} className="relative px-5 py-4 animate-rise" style={{ animationDelay: `${idx * 60}ms` }}>
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-lime-400/30 to-transparent" aria-hidden />
            <div className="flex items-center gap-2">
              <span className="figure text-[10px] text-lime-600">{stage.step}</span>
              <span className="h-px flex-1 bg-paper-200/80" />
              <span className="label-mono text-[8px] text-ink-300">No AI verdicts</span>
            </div>
            <p className="mt-2.5 text-[13px] font-semibold tracking-[-0.01em] text-ink-900">{stage.title}</p>
            <p className="mt-1 text-[11.5px] leading-relaxed text-ink-500">{stage.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
