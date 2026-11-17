"use client";

import Link from "next/link";
import { useState } from "react";

import { LoopMark } from "@/components/icons";

export function PublicHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="absolute inset-x-0 top-0 z-30">
      <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-4 px-5 py-5 sm:px-8">
        <Link
          href="/"
          className="group flex items-center gap-3"
          aria-label="LOOPMESH home"
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-lime-400/30 bg-lime-400/10 text-lime-300 shadow-[0_0_0_1px_rgba(198,243,92,0.08),0_18px_40px_-22px_rgba(198,243,92,0.65)] transition-premium group-hover:bg-lime-400/15">
            <LoopMark className="h-6 w-6" />
          </span>
          <span className="text-[13px] font-semibold tracking-[0.28em] text-paper-50">
            LOOPMESH
          </span>
        </Link>

        <nav aria-label="Public" className="hidden items-center gap-7 md:flex">
          <a
            href="#explore"
            className="text-[12.5px] font-medium text-forest-100/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950 rounded-sm"
          >
            Explore
          </a>
          <a
            href="#platform"
            className="text-[12.5px] font-medium text-forest-100/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950 rounded-sm"
          >
            Platform
          </a>
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/login"
            className="text-[12.5px] font-medium text-forest-100/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950 rounded-sm"
          >
            Sign in
          </Link>
          <Link
            href="/login"
            className="inline-flex h-10 items-center justify-center rounded-lg bg-lime-400 px-4 text-[12.5px] font-semibold tracking-wide text-forest-950 transition-colors hover:bg-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
          >
            Enter LoopMesh
          </Link>
        </div>

        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-forest-700/80 bg-forest-900/40 text-forest-100 md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            {open ? (
              <>
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </>
            ) : (
              <>
                <path d="M4 6h16" />
                <path d="M4 12h16" />
                <path d="M4 18h16" />
              </>
            )}
          </svg>
        </button>
      </div>

      {open ? (
        <div className="mx-5 mb-4 rounded-xl border border-forest-800/80 bg-forest-950/95 px-4 py-4 backdrop-blur md:hidden sm:mx-8">
          <nav aria-label="Public mobile" className="flex flex-col gap-3">
            <a
              href="#explore"
              onClick={() => setOpen(false)}
              className="text-[13px] font-medium text-forest-100 hover:text-paper-50"
            >
              Explore
            </a>
            <a
              href="#platform"
              onClick={() => setOpen(false)}
              className="text-[13px] font-medium text-forest-100 hover:text-paper-50"
            >
              Platform
            </a>
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="text-[13px] font-medium text-forest-100 hover:text-paper-50"
            >
              Sign in
            </Link>
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="mt-1 inline-flex h-10 items-center justify-center rounded-lg bg-lime-400 px-4 text-[12.5px] font-semibold tracking-wide text-forest-950 hover:bg-lime-300"
            >
              Enter LoopMesh
            </Link>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
