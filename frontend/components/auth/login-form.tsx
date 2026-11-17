"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { postJson } from "@/lib/client-api";
import { FORCED_PASSWORD_PATH, safeNextPath, type AuthMessage } from "@/lib/auth";

type FieldErrors = { email?: string; password?: string };

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const fieldClass =
  "h-11 w-full rounded-lg border bg-paper-50 px-3 text-[13px] text-ink-900 outline-none transition-colors placeholder:text-ink-300 focus:bg-white disabled:opacity-60";

function fieldBorder(invalid: boolean): string {
  return invalid
    ? "border-rust-500 focus:border-rust-500"
    : "border-paper-300 focus:border-forest-600";
}

export function LoginForm({
  next,
  initialError,
  disabled = false,
}: {
  next: string;
  initialError?: string | null;
  disabled?: boolean;
}) {
  const router = useRouter();
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(initialError ?? null);
  const [pending, setPending] = useState(false);

  function validate(): FieldErrors {
    const found: FieldErrors = {};
    if (!email.trim()) found.email = "Enter the email address on your account.";
    else if (!EMAIL_PATTERN.test(email.trim()))
      found.email = "Enter a valid email address, for example name@company.com.";
    if (!password) found.password = "Enter your password.";
    return found;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || disabled) return;

    const found = validate();
    setErrors(found);
    setFormError(null);
    if (found.email) {
      emailRef.current?.focus();
      return;
    }
    if (found.password) {
      passwordRef.current?.focus();
      return;
    }

    setPending(true);
    const result = await postJson<AuthMessage>(
      "/auth/login",
      { email: email.trim(), password },
      { retryOnExpiry: false },
    );

    if (!result.ok) {
      setPending(false);
      setFormError(result.error);
      const reason = typeof result.details?.reason === "string" ? result.details.reason : null;
      if (result.code === "invalid_credentials" || reason === "invalid_credentials") {
        setPassword("");
        passwordRef.current?.focus();
      }
      return;
    }

    // Cookies are first-party now; a refresh re-renders the server components
    // with the authenticated principal. An account whose initial password is
    // still operator-issued goes straight to rotation instead of the workspace.
    router.replace(
      result.data.user?.must_change_password ? FORCED_PASSWORD_PATH : safeNextPath(next),
    );
    router.refresh();
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-busy={pending}>
      {formError ? (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-rust-500/30 bg-rust-500/[0.07] px-3 py-2.5 text-[12px] leading-relaxed text-rust-500"
        >
          <svg viewBox="0 0 20 20" aria-hidden className="mt-[1px] h-4 w-4 shrink-0" fill="currentColor">
            <path d="M10 2.5 18.5 17H1.5L10 2.5Zm0 4.2a.9.9 0 0 0-.9 1v3.6a.9.9 0 0 0 1.8 0V7.7a.9.9 0 0 0-.9-1Zm0 7.1a1.05 1.05 0 1 0 0 2.1 1.05 1.05 0 0 0 0-2.1Z" />
          </svg>
          <span>{formError}</span>
        </div>
      ) : null}

      <div>
        <label htmlFor="login-email" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Work email
        </label>
        <input
          ref={emailRef}
          id="login-email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoFocus
          required
          value={email}
          disabled={pending || disabled}
          onChange={(event) => {
            setEmail(event.target.value);
            if (errors.email) setErrors((current) => ({ ...current, email: undefined }));
          }}
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? "login-email-error" : undefined}
          placeholder="name@company.com"
          className={`${fieldClass} ${fieldBorder(Boolean(errors.email))}`}
        />
        {errors.email ? (
          <p id="login-email-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.email}
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="login-password" className="label-mono mb-1.5 block text-[9px] text-ink-400">
          Password
        </label>
        <div className="relative">
          <input
            ref={passwordRef}
            id="login-password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            disabled={pending || disabled}
            onChange={(event) => {
              setPassword(event.target.value);
              if (errors.password) setErrors((current) => ({ ...current, password: undefined }));
            }}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={errors.password ? "login-password-error" : undefined}
            placeholder="Your password"
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
          <p id="login-password-error" className="mt-1.5 text-[11.5px] text-rust-500">
            {errors.password}
          </p>
        ) : null}
      </div>

      <button
        type="submit"
        disabled={pending || disabled}
        className="mt-1 flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-forest-900 text-[12.5px] font-medium tracking-wide text-lime-300 transition-colors hover:bg-forest-800 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {pending ? (
          <>
            <span
              aria-hidden
              className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-lime-300/40 border-t-lime-300"
            />
            Signing in…
          </>
        ) : (
          "Sign in"
        )}
      </button>

      <p aria-live="polite" className="sr-only">
        {pending ? "Signing in, please wait." : ""}
      </p>
    </form>
  );
}
