import type { ReactNode } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { ApiOffline } from "@/components/auth/api-offline";
import { LoopMark } from "@/components/icons";
import { PlatformNav } from "@/components/platform/platform-nav";
import { FORCED_PASSWORD_PATH, displayName } from "@/lib/auth";
import { platformGate } from "@/lib/platform";
import { loadSession, redirectToSignIn } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Server guard for every `/platform` route.
 *
 * The refusal happens before any console markup is produced, so an organisation
 * administrator who edits the URL receives a redirect rather than a flash of
 * platform navigation. The API independently refuses the same requests.
 */
export default async function PlatformLayout({ children }: { children: ReactNode }) {
  const state = await loadSession();
  const gate = platformGate(state);

  if (gate === "offline") {
    return (
      <ApiOffline
        message={state.status === "unavailable" ? state.error : "The LOOPMESH API is not reachable."}
      />
    );
  }
  if (gate === "signed_out") {
    await redirectToSignIn();
    return null;
  }
  if (state.status !== "authenticated") return null;
  if (gate === "password") redirect(FORCED_PASSWORD_PATH);
  if (gate === "workspace") redirect("/overview");

  const user = state.user;

  return (
    <div className="min-h-screen bg-paper-100">
      <header className="border-b border-forest-800 bg-forest-950">
        <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-3">
            <Link href="/platform" className="flex min-w-0 items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-lime-400/10 text-lime-400 ring-1 ring-inset ring-lime-400/25">
                <LoopMark className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block text-[12px] font-semibold tracking-[0.28em] text-paper-50">
                  LOOPMESH
                </span>
                <span className="label-mono block text-[8.5px] text-forest-500">
                  Platform administration
                </span>
              </span>
            </Link>

            <div className="ml-auto flex min-w-0 items-center gap-3">
              <span className="hidden truncate font-mono text-[10px] text-forest-500 sm:inline">
                {displayName(user)}
              </span>
              <Link
                href="/overview"
                className="shrink-0 rounded-lg border border-forest-700 px-2.5 py-1.5 text-[11px] text-paper-200 transition-colors hover:border-forest-600 hover:text-paper-50"
              >
                Organisation workspace
              </Link>
            </div>
          </div>
          <div className="mt-2">
            <PlatformNav permissions={user.permissions} />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] px-4 pb-16 pt-5 sm:px-6">
        <p className="mb-5 rounded-xl border border-clay-500/25 bg-clay-500/[0.06] px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink-600">
          <span className="font-medium text-ink-800">Aggregate and operational metadata only.</span>{" "}
          Tenant materials, proposals, transactions and documents are never shown in this console,
          and every request is authorised again by the API.
        </p>
        {children}
      </main>
    </div>
  );
}
