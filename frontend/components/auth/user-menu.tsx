"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { postJson } from "@/lib/client-api";
import {
  ACCOUNT_PASSWORD_PATH,
  ACCOUNT_SESSIONS_PATH,
  activeMembership,
  displayName,
  initials,
  roleLabel,
  type SessionUser,
} from "@/lib/auth";

export function UserMenu({ user }: { user: SessionUser }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const membership = activeMembership(user);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function signOut() {
    if (pending) return;
    setPending(true);
    setError(null);
    const result = await postJson<{ message: string }>("/auth/logout", {});
    if (!result.ok) {
      setPending(false);
      setError(result.error);
      return;
    }
    // A full navigation drops every client cache entry tied to the old session.
    window.location.assign("/login?reason=signed_out");
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${displayName(user)}`}
        className="flex h-8 items-center gap-2 rounded-full border border-paper-300 bg-paper-50 pl-1 pr-2 transition-colors hover:border-forest-600/40 hover:bg-white"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-forest-900 font-mono text-[9.5px] font-medium text-lime-300">
          {initials(displayName(user))}
        </span>
        <span className="hidden max-w-[110px] truncate text-[11.5px] text-ink-700 sm:inline">
          {displayName(user)}
        </span>
        <svg viewBox="0 0 12 12" aria-hidden className="h-2.5 w-2.5 text-ink-400" fill="currentColor">
          <path d="M6 8.5 1.8 4.3h8.4L6 8.5Z" />
        </svg>
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-50 mt-1.5 w-[286px] overflow-hidden rounded-xl border border-paper-200 bg-[#fffdf8] p-1.5 shadow-[0_18px_40px_-24px_rgba(9,26,20,0.45)] animate-fade"
        >
          <div className="flex items-start gap-2.5 px-2 py-2">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-forest-900 font-mono text-[11px] text-lime-300">
              {initials(displayName(user))}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[12.5px] font-medium text-ink-900">{displayName(user)}</p>
              <p className="mt-0.5 truncate text-[11px] text-ink-500">{user.email}</p>
            </div>
          </div>

          <div className="mx-2 my-1.5 space-y-1 border-y border-paper-200 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="label-mono text-[8.5px] text-ink-400">Role</span>
              <span className="rounded-full border border-paper-300 bg-paper-100 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-ink-700">
                {roleLabel(user.active_role)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="label-mono text-[8.5px] text-ink-400">Organisation</span>
              <span className="max-w-[170px] truncate text-[11px] text-ink-700">
                {membership?.organization_name ?? "—"}
              </span>
            </div>
            {user.is_platform_admin ? (
              <div className="flex items-center justify-between gap-2">
                <span className="label-mono text-[8.5px] text-ink-400">Scope</span>
                <span className="rounded-full bg-forest-900 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-lime-300">
                  Platform admin
                </span>
              </div>
            ) : null}
          </div>

          <Link
            href={ACCOUNT_PASSWORD_PATH}
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12px] text-ink-700 transition-colors hover:bg-paper-100"
          >
            <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5 text-ink-400" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="3" y="7" width="10" height="6.5" rx="1.5" />
              <path d="M5.6 7V5.2a2.4 2.4 0 0 1 4.8 0V7" strokeLinecap="round" />
            </svg>
            Change password
          </Link>
          <Link
            href={ACCOUNT_SESSIONS_PATH}
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12px] text-ink-700 transition-colors hover:bg-paper-100"
          >
            <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5 text-ink-400" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="2.2" y="3" width="11.6" height="7.4" rx="1.4" />
              <path d="M5.6 13.2h4.8M8 10.4v2.8" strokeLinecap="round" />
            </svg>
            Sessions &amp; devices
          </Link>

          <button
            type="button"
            role="menuitem"
            disabled={pending}
            onClick={() => void signOut()}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12px] text-ink-700 transition-colors hover:bg-paper-100 disabled:opacity-60"
          >
            <svg viewBox="0 0 16 16" aria-hidden className="h-3.5 w-3.5 text-ink-400" fill="none" stroke="currentColor" strokeWidth="1.4">
              <path d="M6 2.5H3.2v11H6M10 4.5 13.5 8 10 11.5M13 8H6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {pending ? "Signing out…" : "Sign out"}
          </button>

          {error ? (
            <p role="alert" className="mx-1 mb-1 rounded-md bg-rust-500/[0.08] px-2 py-1.5 text-[11px] leading-relaxed text-rust-500">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
