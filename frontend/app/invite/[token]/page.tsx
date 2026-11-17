import type { Metadata } from "next";
import Link from "next/link";

import { LoopMark } from "@/components/icons";
import { InviteAcceptForm } from "@/components/invitations/invite-accept-form";
import { apiGet } from "@/lib/api";
import { roleLabel } from "@/lib/auth";
import { type Invitation, invitationStatusLabel } from "@/lib/account-types";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Accept invitation",
  description: "Accept your LOOPMESH organisation invitation.",
  robots: { index: false, follow: false },
};

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-paper-100 px-5 py-12 sm:px-8">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.5] tech-grid [mask-image:radial-gradient(circle_at_50%_30%,black,transparent_70%)]"
      />
      <div className="relative w-full max-w-[480px]">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-forest-900 text-lime-400">
            <LoopMark className="h-5 w-5" />
          </span>
          <span className="text-[12px] font-semibold tracking-[0.3em] text-forest-900">LOOPMESH</span>
        </div>
        {children}
        <p className="mt-4 px-1 text-[11px] leading-relaxed text-ink-400">
          Invitations are single-use and expire. A link is a credential — do not forward it.
        </p>
      </div>
    </div>
  );
}

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const preview = await apiGet<Invitation>(
    `/auth/invitations/preview?token=${encodeURIComponent(token)}`,
  );

  if (!preview.ok) {
    return (
      <Shell>
        <div className="panel p-6 sm:p-8">
          <p className="label-mono text-[9px] text-ink-400">Invitation</p>
          <h1 className="mt-2 text-[20px] font-semibold tracking-[-0.015em] text-ink-900">
            This invitation link is not valid
          </h1>
          <p className="mt-2 text-[12.5px] leading-relaxed text-ink-500">
            The link may be incomplete or the invitation may have been removed. Ask the
            organisation administrator to send a new invitation.
          </p>
          <Link
            href="/login"
            className="mt-5 inline-flex h-10 items-center rounded-lg border border-paper-300 bg-paper-50 px-3.5 text-[12px] font-medium text-ink-700 hover:bg-white"
          >
            Go to sign in
          </Link>
        </div>
      </Shell>
    );
  }

  const invitation = preview.data;
  const usable = invitation.status === "pending";

  return (
    <Shell>
      <div className="panel p-6 sm:p-8">
        <p className="label-mono text-[9px] text-ink-400">
          {usable ? "Invitation to join" : "Invitation"}
        </p>
        <h1 className="mt-2 text-[22px] font-semibold tracking-[-0.015em] text-ink-900">
          {invitation.organization_name ?? "An organisation"} on LOOPMESH
        </h1>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-500">
          Role offered: <span className="text-ink-700">{roleLabel(invitation.role)}</span> · expires{" "}
          {formatDate(invitation.expires_at)}
        </p>

        {invitation.note ? (
          <p className="mt-3 rounded-lg border border-paper-300 bg-paper-100 px-3 py-2.5 text-[12px] leading-relaxed text-ink-600">
            “{invitation.note}”
          </p>
        ) : null}

        <div className="mt-5">
          {usable ? (
            <InviteAcceptForm
              token={token}
              email={invitation.email}
              organizationName={invitation.organization_name}
            />
          ) : (
            <div role="status" className="space-y-3 text-[12.5px] leading-relaxed text-ink-700">
              <p className="font-medium text-rust-500">
                This invitation is {invitationStatusLabel(invitation.status).toLowerCase()}.
              </p>
              <p>
                It cannot be used again. Ask the organisation administrator for a new
                invitation, or sign in if your account already exists.
              </p>
              <Link
                href="/login"
                className="inline-flex h-10 items-center rounded-lg border border-paper-300 bg-paper-50 px-3.5 text-[12px] font-medium text-ink-700 hover:bg-white"
              >
                Go to sign in
              </Link>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}
