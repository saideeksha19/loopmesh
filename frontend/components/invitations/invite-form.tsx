"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import { roleLabel } from "@/lib/auth";
import type { Invitation } from "@/lib/account-types";
import { formatDate } from "@/lib/format";

const fieldClass =
  "h-11 w-full rounded-lg border bg-paper-50 px-3 text-[13px] text-ink-900 outline-none transition-colors placeholder:text-ink-300 focus:bg-white disabled:opacity-60";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function InviteMemberForm({
  organizationId,
  organizationName,
  roles,
}: {
  organizationId: string;
  organizationName: string | null;
  roles: { value: string; label: string }[];
}) {
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(roles[0]?.value ?? "viewer");
  const [note, setNote] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<Invitation | null>(null);
  const [copied, setCopied] = useState(false);
  const [pending, setPending] = useState(false);

  const inviteUrl =
    created?.delivery_token && typeof window !== "undefined"
      ? `${window.location.origin}/invite/${created.delivery_token}`
      : null;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    const trimmed = email.trim();
    if (!trimmed) {
      setEmailError("Enter the email address to invite.");
      emailRef.current?.focus();
      return;
    }
    if (!EMAIL_PATTERN.test(trimmed)) {
      setEmailError("Enter a valid email address, for example name@company.com.");
      emailRef.current?.focus();
      return;
    }

    setEmailError(null);
    setFormError(null);
    setPending(true);

    const result = await postJson<Invitation>("/auth/invitations", {
      email: trimmed,
      organization_id: organizationId,
      role,
      scope: "organization",
      note: note.trim() ? note.trim() : null,
    });

    setPending(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }

    setCreated(result.data);
    setEmail("");
    setNote("");
    setCopied(false);
    router.refresh();
  }

  async function copyLink() {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="px-5 py-4 sm:px-6">
      <form onSubmit={submit} noValidate className="grid gap-3 sm:grid-cols-[1.4fr_1fr]" aria-busy={pending}>
        <div>
          <label htmlFor="invite-email" className="label-mono mb-1.5 block text-[9px] text-ink-400">
            Email to invite
          </label>
          <input
            ref={emailRef}
            id="invite-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="off"
            required
            value={email}
            disabled={pending}
            onChange={(event) => {
              setEmail(event.target.value);
              if (emailError) setEmailError(null);
            }}
            aria-invalid={emailError ? true : undefined}
            aria-describedby={emailError ? "invite-email-error" : undefined}
            placeholder="colleague@company.com"
            className={`${fieldClass} ${
              emailError ? "border-rust-500" : "border-paper-300 focus:border-forest-600"
            }`}
          />
          {emailError ? (
            <p id="invite-email-error" className="mt-1.5 text-[11.5px] text-rust-500">
              {emailError}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="invite-role" className="label-mono mb-1.5 block text-[9px] text-ink-400">
            Role in {organizationName ?? "this organisation"}
          </label>
          <select
            id="invite-role"
            name="role"
            value={role}
            disabled={pending}
            onChange={(event) => setRole(event.target.value)}
            className={`${fieldClass} border-paper-300 focus:border-forest-600`}
          >
            {roles.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="invite-note" className="label-mono mb-1.5 block text-[9px] text-ink-400">
            Note for the invitee <span className="text-ink-300">(optional)</span>
          </label>
          <input
            id="invite-note"
            name="note"
            type="text"
            maxLength={280}
            value={note}
            disabled={pending}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why they are joining, or who asked for this access"
            className={`${fieldClass} border-paper-300 focus:border-forest-600`}
          />
        </div>

        <div className="flex items-center gap-3 sm:col-span-2">
          <button
            type="submit"
            disabled={pending}
            className="flex h-10 items-center justify-center gap-2 rounded-lg bg-forest-900 px-4 text-[12px] font-medium tracking-wide text-lime-300 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {pending ? (
              <>
                <span
                  aria-hidden
                  className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-lime-300/40 border-t-lime-300"
                />
                Creating…
              </>
            ) : (
              "Create invitation"
            )}
          </button>
          <p className="text-[11px] leading-relaxed text-ink-400">
            The role is enforced by the API. Any earlier pending invitation for the same address is
            revoked.
          </p>
        </div>
      </form>

      {formError ? (
        <p
          role="alert"
          className="mt-3 rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500"
        >
          {formError}
        </p>
      ) : null}

      {created ? (
        <div
          role="status"
          className="mt-3 rounded-lg border border-forest-700/25 bg-forest-800/[0.06] px-3 py-3 text-[12px] leading-relaxed text-forest-800"
        >
          <p className="font-medium">
            Invitation created for {created.email} as {roleLabel(created.role)}.
          </p>
          <p className="mt-0.5 text-[11.5px] text-ink-600">
            Expires {formatDate(created.expires_at)}. Single use.
          </p>

          {inviteUrl ? (
            <div className="mt-2.5 space-y-2">
              <div className="rounded-md border border-clay-500/30 bg-clay-500/[0.08] px-2.5 py-2 text-[11px] text-clay-500">
                <strong className="font-medium">Development delivery only.</strong> No email provider
                is configured, so the link below is shown once instead of being sent. Treat it as a
                credential: anyone holding it can join as {roleLabel(created.role)}. It is not stored
                in readable form and cannot be shown again.
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-md border border-paper-300 bg-white px-2 py-1.5 font-mono text-[10.5px] text-ink-700">
                  {inviteUrl}
                </code>
                <button
                  type="button"
                  onClick={() => void copyLink()}
                  className="shrink-0 rounded-md border border-paper-300 bg-paper-50 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-600 hover:bg-white"
                >
                  {copied ? "Copied" : "Copy link"}
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-1.5 text-[11.5px] text-ink-600">
              Delivery is handled by the configured provider; the token is not returned to the
              browser in this environment.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
