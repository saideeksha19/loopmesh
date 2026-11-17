import type { Metadata } from "next";

import { PasswordForm } from "@/components/account/password-form";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Password",
  description: "Change the password for your LOOPMESH account.",
  robots: { index: false, follow: false },
};

export default async function AccountPasswordPage() {
  const state = await loadSession();
  if (state.status !== "authenticated") return null;

  const required = state.user.must_change_password;

  return (
    <>
      <PageHeader
        eyebrow="Account security · password"
        title={required ? "Set your own password." : "Change your password."}
        description={
          required
            ? "This account still uses the initial password issued by an administrator. Choose your own to unlock the workspace."
            : "Passwords are stored as hashes only. Changing yours closes every session on the account and requires signing in again."
        }
      />

      <Panel className="p-5 sm:p-6">
        <PasswordForm required={required} />
      </Panel>

      <p className="mt-4 text-[11px] leading-relaxed text-ink-400">
        The server applies the policy again on submission, so a password rejected here would be
        rejected by the API too. The forced-change flag clears only after a successful change.
      </p>
    </>
  );
}
