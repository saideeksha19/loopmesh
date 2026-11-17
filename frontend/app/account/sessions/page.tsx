import type { Metadata } from "next";

import { SessionsPanel } from "@/components/account/sessions-panel";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { apiGet } from "@/lib/api";
import type { SessionInfo } from "@/lib/account-types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sessions",
  description: "Review and revoke the devices signed in to your LOOPMESH account.",
  robots: { index: false, follow: false },
};

export default async function AccountSessionsPage() {
  const response = await apiGet<SessionInfo[]>("/auth/sessions");

  return (
    <>
      <PageHeader
        eyebrow="Account security · sessions"
        title="Devices signed in to this account."
        description="Each sign-in is its own session with its own HttpOnly cookies. Revoking one signs that device out without touching the others; revoking every other session keeps this one open."
      />

      {response.ok ? (
        <Panel>
          <SessionsPanel initialSessions={response.data} />
        </Panel>
      ) : (
        <DataUnavailable message={response.error} title="Sessions unavailable" />
      )}

      <p className="mt-4 text-[11px] leading-relaxed text-ink-400">
        Session listings never include access or refresh tokens. Revocation is recorded against the
        session server-side, so a revoked cookie stops working immediately rather than at its next
        expiry.
      </p>
    </>
  );
}
