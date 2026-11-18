import { PublicHeader } from "./public-header";
import { Hero } from "./hero";
import { HowItWorksSection } from "./how-it-works-section";
import { HighlightsSection } from "./highlights-section";
import { NetworkSection } from "./network-section";
import { ProblemSection } from "./problem-section";
import { TransformationSection } from "./transformation-section";
import { ResourceExplorer } from "./resource-explorer";
import { PlatformCapabilities } from "./platform-capabilities";
import { ImpactSection } from "./impact-section";
import { TrustGovernanceSection } from "./trust-governance-section";
import { FinaleSection } from "./finale-section";
import { PublicFooter } from "./public-footer";
import { Reveal } from "./reveal";
import { SectionConnector } from "./section-connector";

export function HomePage() {
  return (
    <div className="min-h-screen bg-forest-950 text-paper-50">
      <PublicHeader />
      <main id="main-content">
        <Hero />

        <Reveal>
          <HowItWorksSection />
        </Reveal>

        <Reveal>
          <HighlightsSection />
        </Reveal>

        <SectionConnector tone="lime" />

        <Reveal>
          <NetworkSection />
        </Reveal>

        <SectionConnector tone="teal" />

        <div id="explore" className="scroll-mt-24">
          <Reveal>
            <ProblemSection />
          </Reveal>
          <Reveal>
            <TransformationSection />
          </Reveal>
          <Reveal>
            <section
              aria-labelledby="explorer-heading"
              className="border-t border-forest-800/60 bg-[linear-gradient(180deg,#0f2418_0%,#10291a_100%)] px-5 py-24 sm:px-8 sm:py-28 lg:px-10"
            >
              <div className="mx-auto max-w-[1440px]">
                <p className="label-mono text-[10px] tracking-[0.22em] text-lime-300/80">
                  Explore the Network
                </p>
                <h2
                  id="explorer-heading"
                  className="mt-4 max-w-3xl text-[clamp(2rem,4.4vw,3.5rem)] font-semibold leading-[1.08] tracking-[-0.03em] text-paper-50"
                >
                  See how material exchange and resource discovery can connect.
                </h2>
                <p className="mt-6 max-w-2xl text-[14px] leading-relaxed text-forest-100/80 sm:text-[16px]">
                  Explore an illustrative view of potential energy, water, and material exchanges.
                  Examples below are for demonstration only and do not represent real operational
                  data.
                </p>
                <ResourceExplorer />
              </div>
            </section>
          </Reveal>
        </div>

        <Reveal>
          <PlatformCapabilities />
        </Reveal>

        <Reveal>
          <ImpactSection />
        </Reveal>

        <SectionConnector tone="amber" />

        <Reveal>
          <TrustGovernanceSection />
        </Reveal>

        <SectionConnector tone="lime" />

        <Reveal>
          <FinaleSection />
        </Reveal>
      </main>
      <PublicFooter />
    </div>
  );
}
