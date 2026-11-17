import { PublicHeader } from "./public-header";
import { Hero } from "./hero";
import { ProblemSection } from "./problem-section";
import { TransformationSection } from "./transformation-section";
import { ResourceExplorer } from "./resource-explorer";
import { PlatformCapabilities } from "./platform-capabilities";
import { ImpactSection } from "./impact-section";
import { TrustGovernanceSection } from "./trust-governance-section";
import { FinaleSection } from "./finale-section";
import { PublicFooter } from "./public-footer";

export function HomePage() {
  return (
    <div className="min-h-screen bg-forest-950 text-paper-50">
      <PublicHeader />
      <main>
        <Hero />
        <div id="explore">
          <ProblemSection />
          <TransformationSection />
          <section
            aria-labelledby="explorer-heading"
            className="border-t border-forest-800/60 bg-[linear-gradient(180deg,#0f2418_0%,#10291a_100%)] px-5 py-24 sm:px-8 sm:py-28"
          >
            <div className="mx-auto max-w-[1440px]">
              <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">Interactive resource explorer</p>
              <h2
                id="explorer-heading"
                className="mt-4 max-w-3xl text-[clamp(2rem,4.5vw,3.5rem)] font-semibold leading-[1.1] tracking-[-0.03em] text-paper-50"
              >
                Explore illustrative energy,
                <br />
                <span className="text-lime-300/90">water, and material exchanges.</span>
              </h2>
              <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
                Select a flow type or a facility node to see how potential connections could be understood. All examples below are illustrative and do not represent real operational data.
              </p>
              <ResourceExplorer />
            </div>
          </section>
        </div>
        <PlatformCapabilities />
        <ImpactSection />
        <TrustGovernanceSection />
        <FinaleSection />
      </main>
      <PublicFooter />
    </div>
  );
}
