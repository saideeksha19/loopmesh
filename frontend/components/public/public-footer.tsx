import Link from "next/link";

import { LoopMark } from "@/components/icons";

export function PublicFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-forest-800/80 bg-forest-950 px-5 py-14 sm:px-8">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm">
            <Link href="/" className="flex items-center gap-3" aria-label="LOOPMESH home">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-lime-400/25 bg-lime-400/10 text-lime-300">
                <LoopMark className="h-6 w-6" />
              </span>
              <span className="text-[13px] font-semibold tracking-[0.28em] text-paper-50">LOOPMESH</span>
            </Link>
            <p className="mt-4 text-[12.5px] leading-relaxed text-forest-300/90">
              Industrial symbiosis intelligence for connecting resources, workflows, and verified recovery.
            </p>
          </div>
          <nav aria-label="Footer" className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-x-8 sm:gap-y-3">
            <a
              href="#explore"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Explore
            </a>
            <a
              href="#platform"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Platform
            </a>
            <Link
              href="/login"
              className="text-[12.5px] text-forest-200/90 transition-colors hover:text-paper-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-lime-400/60 rounded-sm"
            >
              Sign in
            </Link>
          </nav>
        </div>
        <div className="mt-12 border-t border-forest-800/80 pt-8">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-forest-400/80">
            © {year} LoopMesh. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
