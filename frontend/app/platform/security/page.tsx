import type { Metadata } from "next";

import { MfaPanel } from "@/components/platform/mfa-panel";
import { OperatorSessions } from "@/components/platform/operator-sessions";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import { PLATFORM_PERMISSION, canPlatform } from "@/lib/platform";
import type {
  MfaStatus,
  PlatformOperatorSession,
} from "@/lib/platform-types";
import { loadSession } from "@/lib/session";
import type { Page } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Operator security",
  description: "Two-factor authentication and platform session governance.",
  robots: { index: false, follow: false },
};

export default async function PlatformSecurityPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;
  const user = state.user;

  const canManageSessions = canPlatform(user, PLATFORM_PERMISSION.sessionsManage);
  const [mfaResponse, sessionResponse] = await Promise.all([
    apiGet<MfaStatus>("/auth/mfa/status"),
    canManageSessions
      ? apiGet<Page<PlatformOperatorSession>>("/platform/sessions?page_size=50")
      : Promise.resolve(null),
  ]);

  return (
    <>
      <PageHeader
        eyebrow="Platform · operator security"
        title="The second factor is not optional."
        description="Platform capabilities are granted to an account, but they are usable only from a session that has presented a second factor and remains inside the idle and absolute limits. Enrolment is available before any other console capability."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            eyebrow="Authentication"
            title="Authenticator app"
            subtitle="TOTP, verified by the API on every platform request. Recovery codes are hashed, single-use and shown exactly once."
          />
          <div className="px-4 py-4 sm:px-6">
            {!mfaResponse.ok ? (
              <DataUnavailable
                title="MFA status unavailable"
                message={mfaResponse.error}
                hint="The console does not infer that MFA is active or inactive when the API cannot answer."
              />
            ) : (
              <MfaPanel status={mfaResponse.data} />
            )}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            eyebrow="Sessions"
            title="Operator sessions"
            subtitle="Platform-flagged accounts only. Ordinary organisation sessions are outside this governance surface."
          />
          <div className="px-4 py-4 sm:px-6">
            {!canManageSessions ? (
              <p className="text-[11.5px] leading-relaxed text-ink-500">
                Session inventory and revocation need{" "}
                <code className="font-mono text-[10px]">platform.sessions.manage</code>. Your
                account is a platform operator without that capability; the API refuses both list
                and revocation.
              </p>
            ) : !sessionResponse?.ok ? (
              <DataUnavailable
                title="Operator sessions unavailable"
                message={sessionResponse?.error ?? "The API did not answer."}
                hint="No session is shown rather than a guessed inventory."
              />
            ) : (
              <OperatorSessions sessions={sessionResponse.data.items} />
            )}
          </div>
        </Panel>
      </div>

      <Panel className="mt-4 p-4 sm:p-5">
        <p className="text-[11.5px] leading-relaxed text-ink-600">
          <span className="font-medium text-ink-800">Recovery without a support bypass.</span> An
          operator who loses both the authenticator and their recovery codes cannot self-enrol a new
          factor: there is no unauthenticated reset route. A deployment operator must use the
          documented server-side procedure, with database access, and the account&apos;s platform flag
          is reviewed at the same time. LOOPMESH never sends an MFA code by email or SMS, and no
          provider is configured or implied.
        </p>
      </Panel>
    </>
  );
}
