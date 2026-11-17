"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import type { AuthMessage } from "@/lib/auth";
import { passwordChecks, passwordProblem } from "@/lib/password-policy";

const fieldClass =
  "h-11 w-full rounded-lg border bg-paper-50 px-3 text-[13px] text-ink-900 outline-none transition-colors placeholder:text-ink-300 focus:bg-white disabled:opacity-60";

function fieldBorder(invalid: boolean): string {
  return invalid
    ? "border-rust-500 focus:border-rust-500"
    : "border-paper-300 focus:border-forest-600";
}

type FieldErrors = { fullName?: string; password?: string; confirm?: string };

/**
 * Invitation acceptance.
 *
 * The API decides whether the token is still usable, applies the password
 * policy and creates the account and membership in one transaction. This form
 * only mirrors the checks so the invitee learns about a problem before a round
 * trip, and it never sends anything but the token, a name and a password.
 */
export function InviteAcceptForm({
  token,
  email,
  organizationName,
}: {
  token: string;
  email: string;
  organizationName: string | null;
}) {
  const router = useRouter();
  const nameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [invalidToken, setInvalidToken] = useState(false);
  const [pending, setPending] = useState(false);

  const checks = passwordChecks(password);

  function validate(): FieldErrors {
    const found: FieldErrors = {};
    if (fullName.trim().length < 2) found.fullName = "Enter your full name.";
    const problem = passwordProblem(password);
    if (!password) found.password = "Choose a password.";
    else if (problem) found.password = `Password needs: ${problem.toLowerCase()}.`;
    if (!confirm) found.confirm = "Repeat the password.";
    else if (confirm !== password) found.confirm = "The passwords do not match.";
    return found;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    const found = validate();
    setErrors(found);
    setFormError(null);
    if (found.fullName) {
      nameRef.current?.focus();
      return;
    }
    if (found.password) {
      passwordRef.current?.focus();
      return;
    }
    if (found.confirm) {
      confirmRef.current?.focus();
      return;
    }

    setPending(true);
    const result = await postJson<AuthMessage>(
      "/auth/invitations/accept",
      { token, full_name: fullName.trim(), password },
      { retryOnExpiry: false },
    );

    if (!result.ok) {
      setPending(false);
      setFormError(result.error);
      if (result.code === "invalid_invitation" || result.details?.reason === "invalid_invitation") {
        setInvalidToken(true);
      }
      return;
    }

    // Acceptance signs the new member in; the workspace is the next step.
    router.replace("/");
    router.refresh();
  }

  if (invalidToken) {
    return (
      <div role="alert" className="space-y-3 text-[12.5px] leading-relaxed text-ink-700">
        <p className="font-medium text-rust-500">This invitation can no longer be used.</p>
        <p>
          It may have expired, already been accepted, or been revoked by the organisation
          administrator. Ask them to issue a new invitation.
        </p>
        <a
          href="/login"
          className="inline-flex h-10 items-center rounded-lg border border-paper-300 bg-paper-50 px-3.5 text-[12px] font-medium text-ink-700 hover:bg-white"
        >
          Go to sign in
        </a>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-busy={pending}>
      <p className="rounded-lg border border-paper-300 bg-paper-100 px-3 py-2.5 text-[12px] leading-relaxed text-ink-600">
        You are joining <strong className="font-medium text-ink-900">{organizationName ?? "this organisation"}</strong> as{" "}
        <span className="font-mono text-[11px] text-ink-700">{email}</span>. Choose your own
        password — it is never shown or reused by an administrator.
      </p>

      {formError ? (
        <div
          role="alert"
          className="rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500"
        >
          {formError}
        </div>
      ) : null}

      <div>
        <label htmlFor="invite-name" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Full name
        </label>
        <input
          ref={nameRef}
          id="invite-name"
          name="full_name"
          type="text"
          autoComplete="name"
          autoFocus
          required
          value={fullName}
          disabled={pending}
          onChange={(event) => {
            setFullName(event.target.value);
            if (errors.fullName) setErrors((current) => ({ ...current, fullName: undefined }));
          }}
          aria-invalid={errors.fullName ? true : undefined}
          aria-describedby={errors.fullName ? "invite-name-error" : undefined}
          placeholder="Ada Ortega"
          className={`${fieldClass} ${fieldBorder(Boolean(errors.fullName))}`}
        />
        {errors.fullName ? (
          <p id="invite-name-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.fullName}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="invite-password" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Choose a password
        </label>
        <div className="relative">
          <input
            ref={passwordRef}
            id="invite-password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            required
            value={password}
            disabled={pending}
            onChange={(event) => {
              setPassword(event.target.value);
              if (errors.password) setErrors((current) => ({ ...current, password: undefined }));
            }}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? "invite-password-error" : "invite-password-rules"}
            placeholder="At least 12 characters"
            className={`${fieldClass} pr-20 ${fieldBorder(Boolean(errors.password))}`}
          />
          <button
            type="button"
            onClick={() => setShowPassword((current) => !current)}
            aria-pressed={showPassword}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 font-mono text-[9.5px] uppercase tracking-wider text-ink-400 transition-colors hover:bg-paper-200 hover:text-ink-700"
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
        {errors.password ? (
          <p id="invite-password-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.password}
          </p>
        ) : null}
        <ul id="invite-password-rules" className="mt-2 grid gap-1 sm:grid-cols-2">
          {checks.map((check) => (
            <li
              key={check.id}
              className={[
                "flex items-center gap-1.5 text-[11px]",
                check.met ? "text-forest-700" : "text-ink-400",
              ].join(" ")}
            >
              <span
                aria-hidden
                className={[
                  "h-1.5 w-1.5 rounded-full",
                  check.met ? "bg-forest-600" : "bg-ink-300",
                ].join(" ")}
              />
              {check.label}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <label htmlFor="invite-confirm" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Repeat password
        </label>
        <input
          ref={confirmRef}
          id="invite-confirm"
          name="confirm_password"
          type={showPassword ? "text" : "password"}
          autoComplete="new-password"
          required
          value={confirm}
          disabled={pending}
          onChange={(event) => {
            setConfirm(event.target.value);
            if (errors.confirm) setErrors((current) => ({ ...current, confirm: undefined }));
          }}
          aria-invalid={errors.confirm ? true : undefined}
          aria-describedby={errors.confirm ? "invite-confirm-error" : undefined}
          placeholder="Repeat the password"
          className={`${fieldClass} ${fieldBorder(Boolean(errors.confirm))}`}
        />
        {errors.confirm ? (
          <p id="invite-confirm-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.confirm}
          </p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={pending}
        className="mt-1 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-forest-900 text-[12.5px] font-medium tracking-wide text-lime-300 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {pending ? (
          <>
            <span
              aria-hidden
              className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-lime-300/40 border-t-lime-300"
            />
            Creating your account…
          </>
        ) : (
          "Accept invitation"
        )}
      </button>

      <p aria-live="polite" className="sr-only">
        {pending ? "Creating your account, please wait." : ""}
      </p>
    </form>
  );
}
