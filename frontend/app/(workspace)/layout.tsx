import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { ApiOffline } from "@/components/auth/api-offline";
import { SessionKeeper } from "@/components/auth/session-keeper";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";
import { apiGet } from "@/lib/api";
import { FORCED_PASSWORD_PATH } from "@/lib/auth";
import { loadSession, redirectToSignIn } from "@/lib/session";
import type { HealthResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children }: { children: ReactNode }) {
  const state = await loadSession();

  if (state.status !== "authenticated") {
    if (state.status === "unavailable") return <ApiOffline message={state.error} />;
    await redirectToSignIn();
    return null;
  }

  const user = state.user;

  // An initial password issued by an operator must be replaced before any
  // workspace data is rendered. The API refuses the same requests, so this is
  // the redirect that makes the rule navigable rather than a bare 403.
  if (user.must_change_password) redirect(FORCED_PASSWORD_PATH);

  const health = await apiGet<HealthResponse>("/health");

  return (
    <div className="min-h-screen bg-paper-100 lg:flex">
      <SessionKeeper expiresAt={user.session_expires_at} />
      <Sidebar apiOnline={health.ok} permissions={user.permissions} />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
          <div className="absolute -top-24 right-[-10%] h-72 w-72 rounded-full bg-lime-400/[0.07] blur-3xl" />
          <div className="absolute top-40 left-[-5%] h-64 w-64 rounded-full bg-teal-500/[0.06] blur-3xl" />
        </div>
        <TopBar apiOnline={health.ok} user={user} />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-5 pb-16 pt-6 sm:px-8 lg:pt-8">
          <div className="animate-fade">{children}</div>
        </main>
      </div>
    </div>
  );
}
