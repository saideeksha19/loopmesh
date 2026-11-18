import Link from "next/link";

import { LoopMark } from "@/components/icons";

export function PublicFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-forest-800/80 bg-forest-950 px-5 py-14 sm:px-8 lg:px-10">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid gap-10 md:grid-cols-[1.2fr_1fr_1fr] md:items-start">
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-3" aria-label="LOOPMESH home">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-lime-400/25 bg-lime-400/10 text-lime-300">
                <LoopMark className="h-6 w-6" />
              </span>
              <span className="text-[13px] font-semibold tracking-[0.28em] text-paper-50">
                LOOPMESH
              </span>
            </Link>
            <p className="mt-4 text-[13px] leading-relaxed text-forest-300/90">
              Transform industrial surplus into valuable resources. LOOPMESH connects businesses for
              material exchange, resource discovery, opportunities, and transparent transactions
              across a more circular industrial economy.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/login"
                className="inline-flex h-10 items-center justify-center rounded-lg bg-lime-400 px-4 text-[12px] font-semibold text-forest-950 transition-colors hover:bg-lime-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
              >
                Get Started
              </Link>
              <Link
                href="/login"
                className="inline-flex h-10 items-center justify-center rounded-lg border border-forest-700/80 px-4 text-[12px] font-medium text-paper-50 transition-colors hover:border-forest-500 hover:bg-forest-900/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-forest-950"
              >
                Sign In
              </Link>
            </div>
          </div>

          <nav aria-label="Explore" className="flex flex-col gap-3">
            <p className="label-mono text-[10px] tracking-[0.18em] text-forest-400">Explore</p>
            <a
              href="#how-it-works"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              How it works
            </a>
            <a
              href="#explore"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Explore the Network
            </a>
            <a
              href="#highlights"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Highlights
            </a>
            <a
              href="#platform"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Platform capabilities
            </a>
          </nav>

          <div className="flex flex-col gap-3">
            <p className="label-mono text-[10px] tracking-[0.18em] text-forest-400">Access</p>
            <Link
              href="/login"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Sign in to workspace
            </Link>
            <p className="mt-2 max-w-xs text-[12px] leading-relaxed text-forest-400/90">
              Authenticated users continue in the existing LOOPMESH application with their current
              permissions, workflows, and data.
            </p>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-forest-800/80 pt-8 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-forest-400/80">
            © {year} LoopMesh. All rights reserved.
          </p>
          <p className="text-[11px] text-forest-500">
            Built for secure, governed, and transparent industrial resource recovery.
          </p>
        </div>
      </div>
    </footer>
  );
}
