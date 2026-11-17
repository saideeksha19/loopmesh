"use client";

import { useEffect, useRef, useState } from "react";
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

type FieldErrors = { currentPassword?: string; newPassword?: string; confirm?: string };

/**
 * Password change.
 *
 * The API verifies the current password, applies the policy and closes every
 * session of the account. `must_change_password` can only be cleared by a
 * successful rotation, so this form is the only way out of the locked state.
 */
export function PasswordForm({ required }: { required: boolean }) {
  const router = useRouter();
  const currentRef = useRef<HTMLInputElement>(null);
  const nextRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [focusRequest, setFocusRequest] = useState<keyof FieldErrors | null>(null);

  const checks = passwordChecks(newPassword);

  // Inputs are disabled while a request is in flight, so an immediate focus()
  // call is a no-op. Focus after the re-render that re-enables them.
  useEffect(() => {
    if (!focusRequest) return;
    const target =
      focusRequest === "currentPassword"
        ? currentRef
        : focusRequest === "newPassword"
          ? nextRef
          : confirmRef;
    target.current?.focus();
    setFocusRequest(null);
  }, [focusRequest]);

  function validate(): FieldErrors {
    const found: FieldErrors = {};
    if (!currentPassword) found.currentPassword = "Enter your current password.";
    const problem = passwordProblem(newPassword);
    if (!newPassword) found.newPassword = "Choose a new password.";
    else if (problem) found.newPassword = `Password needs: ${problem.toLowerCase()}.`;
    else if (newPassword === currentPassword)
      found.newPassword = "Choose a password you have not used here before.";
    if (!confirm) found.confirm = "Repeat the new password.";
    else if (confirm !== newPassword) found.confirm = "The passwords do not match.";
    return found;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;

    const found = validate();
    setErrors(found);
    setFormError(null);
    if (found.currentPassword) {
      setFocusRequest("currentPassword");
      return;
    }
    if (found.newPassword) {
      setFocusRequest("newPassword");
      return;
    }
    if (found.confirm) {
      setFocusRequest("confirm");
      return;
    }

    setPending(true);
    // A wrong current password is a 401 by contract, so this request must not
    // be mistaken for an expired session and silently retried after a refresh.
    const result = await postJson<AuthMessage>(
      "/auth/change-password",
      { current_password: currentPassword, new_password: newPassword },
      { retryOnExpiry: false },
    );

    if (!result.ok) {
      setPending(false);
      const reason = typeof result.details?.reason === "string" ? result.details.reason : null;
      const field = typeof result.details?.field === "string" ? result.details.field : null;

      if (field === "current_password") {
        setFormError(result.error);
        setCurrentPassword("");
        setFocusRequest("currentPassword");
        return;
      }

      if (reason && reason.startsWith("session")) {
        // The session is gone; the form can never succeed, so recover instead.
        router.replace("/login?reason=session_expired");
        return;
      }

      setFormError(result.error);
      if (result.code === "weak_password") setFocusRequest("newPassword");
      return;
    }

    // Every session was revoked by the change, so the only sane next step is
    // signing in again with the new password.
    router.replace("/login?reason=password_changed");
    router.refresh();
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-busy={pending}>
      {required ? (
        <div
          role="status"
          className="rounded-lg border border-clay-500/30 bg-clay-500/[0.08] px-3 py-2.5 text-[12px] leading-relaxed text-clay-500"
        >
          Your account was created with an initial password by an administrator. Set your own
          password to open the workspace — the API refuses every workspace request until you do.
        </div>
      ) : null}

      {formError ? (
        <div
          role="alert"
          className="rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500"
        >
          {formError}
        </div>
      ) : null}

      <div>
        <label htmlFor="password-current" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Current password
        </label>
        <input
          ref={currentRef}
          id="password-current"
          name="current_password"
          type="password"
          autoComplete="current-password"
          required
          value={currentPassword}
          disabled={pending}
          onChange={(event) => {
            setCurrentPassword(event.target.value);
            if (errors.currentPassword)
              setErrors((current) => ({ ...current, currentPassword: undefined }));
          }}
          aria-invalid={errors.currentPassword ? true : undefined}
          aria-describedby={errors.currentPassword ? "password-current-error" : undefined}
          className={`${fieldClass} ${fieldBorder(Boolean(errors.currentPassword))}`}
        />
        {errors.currentPassword ? (
          <p id="password-current-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.currentPassword}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="password-new" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          New password
        </label>
        <input
          ref={nextRef}
          id="password-new"
          name="new_password"
          type="password"
          autoComplete="new-password"
          required
          value={newPassword}
          disabled={pending}
          onChange={(event) => {
            setNewPassword(event.target.value);
            if (errors.newPassword) setErrors((current) => ({ ...current, newPassword: undefined }));
          }}
          aria-invalid={errors.newPassword ? true : undefined}
          aria-describedby={errors.newPassword ? "password-new-error" : "password-new-rules"}
          className={`${fieldClass} ${fieldBorder(Boolean(errors.newPassword))}`}
        />
        {errors.newPassword ? (
          <p id="password-new-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.newPassword}
          </p>
        ) : null}
        <ul id="password-new-rules" className="mt-2 grid gap-1 sm:grid-cols-2">
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
                className={["h-1.5 w-1.5 rounded-full", check.met ? "bg-forest-600" : "bg-ink-300"].join(
                  " ",
                )}
              />
              {check.label}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <label htmlFor="password-confirm" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Repeat new password
        </label>
        <input
          ref={confirmRef}
          id="password-confirm"
          name="confirm_password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          disabled={pending}
          onChange={(event) => {
            setConfirm(event.target.value);
            if (errors.confirm) setErrors((current) => ({ ...current, confirm: undefined }));
          }}
          aria-invalid={errors.confirm ? true : undefined}
          aria-describedby={errors.confirm ? "password-confirm-error" : undefined}
          className={`${fieldClass} ${fieldBorder(Boolean(errors.confirm))}`}
        />
        {errors.confirm ? (
          <p id="password-confirm-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.confirm}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <button
          type="submit"
          disabled={pending}
          className="flex h-11 items-center justify-center gap-2 rounded-lg bg-forest-900 px-5 text-[12.5px] font-medium tracking-wide text-lime-300 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-70"
        >
          {pending ? (
            <>
              <span
                aria-hidden
                className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-lime-300/40 border-t-lime-300"
              />
              Updating…
            </>
          ) : (
            "Change password"
          )}
        </button>
        <p className="text-[11px] leading-relaxed text-ink-400">
          Changing your password signs out every session, including this one.
        </p>
      </div>

      <p aria-live="polite" className="sr-only">
        {pending ? "Updating your password, please wait." : ""}
      </p>
    </form>
  );
}
