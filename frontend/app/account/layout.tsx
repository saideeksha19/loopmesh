import type { ReactNode } from "react";
import Link from "next/link";

import { AccountNav } from "@/components/account/account-nav";
import { ApiOffline } from "@/components/auth/api-offline";
import { SessionKeeper } from "@/components/auth/session-keeper";
import { LoopMark } from "@/components/icons";
import { displayName } from "@/lib/auth";
import { loadSession, redirectToSignIn } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Account security shell.
 *
 * Deliberately outside the workspace layout: an account awaiting a password
 * change is redirected away from every workspace route, so hosting this page
 * inside the workspace would redirect to itself forever.
 */
export default async function AccountLayout({ children }: { children: ReactNode }) {
  const state = await loadSession();

  if (state.status !== "authenticated") {
    if (state.status === "unavailable") return <ApiOffline message={state.error} />;
    await redirectToSignIn();
    return null;
  }

  const user = state.user;

  return (
    <div className="min-h-screen bg-paper-100">
      <SessionKeeper expiresAt={user.session_expires_at} />

      <header className="border-b border-paper-200 bg-paper-100/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-[860px] items-center gap-3 px-5 sm:px-8">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-forest-900 text-lime-400">
            <LoopMark className="h-4.5 w-4.5" />
          </span>
          <div className="min-w-0">
            <p className="label-mono text-[9px] text-ink-400">LOOPMESH account</p>
            <p className="truncate text-[13px] font-medium text-ink-900">
              {displayName(user)} · {user.email}
            </p>
          </div>

          <div className="ml-auto">
            {user.must_change_password ? (
              <span className="rounded-full border border-clay-500/30 bg-clay-500/10 px-2.5 py-1 font-mono text-[9.5px] uppercase tracking-wider text-clay-500">
                Workspace locked
              </span>
            ) : (
              <Link
                href="/overview"
                className="rounded-lg border border-paper-300 bg-paper-50 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-500 transition-colors hover:bg-paper-100"
              >
                Back to workspace
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="border-b border-paper-200 bg-paper-100">
        <div className="mx-auto w-full max-w-[860px] px-5 py-3 sm:px-8">
          <AccountNav />
        </div>
      </div>

      <main className="mx-auto w-full max-w-[860px] px-5 pb-16 pt-7 sm:px-8">{children}</main>
    </div>
  );
}
