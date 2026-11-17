import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/auth/login-form";
import { LoopMark } from "@/components/icons";
import { LOGIN_REASON_COPY, safeNextPath } from "@/lib/auth";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the LOOPMESH industrial symbiosis workspace.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; reason?: string }>;
}) {
  const params = await searchParams;
  const next = safeNextPath(params.next);
  const state = await loadSession();

  if (state.status === "authenticated") redirect(next);

  const reasonCopy = params.reason ? (LOGIN_REASON_COPY[params.reason] ?? null) : null;
  const apiUnavailable = state.status === "unavailable";

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-forest-950 px-12 py-11 lg:flex lg:flex-col lg:justify-between xl:px-16">
        <div className="tech-grid-dark absolute inset-0 opacity-60" aria-hidden />
        <div
          aria-hidden
          className="absolute -right-24 top-1/3 h-[420px] w-[420px] rounded-full bg-lime-400/[0.07] blur-3xl"
        />

        <div className="relative">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-lime-400/10 text-lime-400 ring-1 ring-inset ring-lime-400/25">
              <LoopMark className="h-6 w-6" />
            </span>
            <span>
              <span className="block text-[13px] font-semibold tracking-[0.3em] text-paper-50">
                LOOPMESH
              </span>
              <span className="label-mono mt-1 block text-[9px] text-forest-500">
                Industrial symbiosis OS
              </span>
            </span>
          </div>

          <h1 className="mt-16 max-w-[430px] text-[42px] leading-[1.06] tracking-[-0.01em] text-paper-50 font-[family-name:var(--font-instrument)] xl:text-[46px]">
            What one industry discards,
            <span className="text-lime-300 italic"> another can use.</span>
          </h1>
          <p className="mt-5 max-w-[380px] text-[13px] leading-relaxed text-forest-500">
            Deterministic compatibility rules, measured material profiles and a ledger that only
            credits verified recovery.
          </p>

          <ul className="mt-10 space-y-3.5">
            {[
              ["Tenant-scoped intelligence", "You see your organisation’s streams and the counterparties you trade with. Nothing else."],
              ["Role-bound workflow", "Coordinators propose, reviewers assess, approvers authorise, auditors verify."],
              ["Evidence-backed ledger", "Recovery is credited only after a verified transfer, never on a match."],
            ].map(([title, detail]) => (
              <li key={title} className="flex gap-3">
                <span className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-lime-400" aria-hidden />
                <span>
                  <span className="block text-[12.5px] font-medium text-paper-200">{title}</span>
                  <span className="mt-0.5 block max-w-[340px] text-[11.5px] leading-relaxed text-forest-500">
                    {detail}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative mt-12 max-w-[360px] font-mono text-[9.5px] uppercase leading-relaxed tracking-[0.14em] text-forest-600">
          Sessions are held in HttpOnly cookies. Authorisation is decided by the API on every
          request.
        </p>
      </aside>

      <main className="relative flex items-center justify-center bg-paper-100 px-5 py-12 sm:px-10">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.5] tech-grid [mask-image:radial-gradient(circle_at_50%_35%,black,transparent_70%)]"
        />
        <div className="relative w-full max-w-[420px]">
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-forest-900 text-lime-400">
              <LoopMark className="h-5 w-5" />
            </span>
            <span className="text-[12px] font-semibold tracking-[0.3em] text-forest-900">LOOPMESH</span>
          </div>

          <div className="panel p-6 sm:p-8">
            <p className="label-mono text-[9px] text-ink-400">Secure workspace access</p>
            <h2 className="mt-2 text-[22px] font-semibold tracking-[-0.015em] text-ink-900">
              Sign in to LOOPMESH
            </h2>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-500">
              Use the account issued by your organisation administrator.
            </p>

            {reasonCopy ? (
              <div
                role="status"
                className="mt-4 flex items-start gap-2.5 rounded-lg border border-paper-300 bg-paper-100 px-3 py-2.5 text-[12px] leading-relaxed text-ink-700"
              >
                <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full bg-ink-400" aria-hidden />
                <span>{reasonCopy}</span>
              </div>
            ) : null}

            {apiUnavailable ? (
              <div
                role="alert"
                className="mt-4 rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500"
              >
                The LOOPMESH API is not reachable, so sign-in cannot complete. Start the backend
                and reload this page.
              </div>
            ) : null}

            <div className="mt-5">
              <LoginForm next={next} disabled={apiUnavailable} />
            </div>
          </div>

          <p className="mt-4 px-1 text-[11px] leading-relaxed text-ink-400">
            Access is limited to the organisations you hold an active membership in. Role
            permissions and tenant isolation are enforced server-side.
          </p>
        </div>
      </main>
    </div>
  );
}
