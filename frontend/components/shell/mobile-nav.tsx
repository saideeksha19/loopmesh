"use client";

import { useEffect, useState } from "react";

import { CloseIcon, LoopMark, MenuIcon } from "@/components/icons";
import { SidebarContent } from "@/components/shell/sidebar-content";

export function MobileNav({
  apiOnline,
  permissions,
}: {
  apiOnline: boolean;
  permissions: string[];
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="flex h-9 w-9 items-center justify-center rounded-xl border border-paper-300/70 bg-paper-50/90 text-ink-700 shadow-sm transition-premium hover:border-forest-600/30 hover:bg-paper-50"
      >
        <MenuIcon className="h-[18px] w-[18px]" />
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-forest-950/65 backdrop-blur-sm animate-fade"
          />
          <div className="animate-drawer relative ml-0 h-full w-[292px] max-w-[86vw] overflow-y-auto border-r border-forest-800/70 bg-forest-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-forest-800/80 px-4 py-3">
              <span className="flex items-center gap-2 text-[11px] tracking-[0.26em] text-paper-50">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-lime-400/10 text-lime-400 ring-1 ring-inset ring-lime-400/25">
                  <LoopMark className="h-4 w-4" />
                </span>
                LOOPMESH
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="flex h-8 w-8 items-center justify-center rounded-md text-ink-400/80 transition-premium hover:bg-white/5 hover:text-paper-100"
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            </div>
            <SidebarContent
              apiOnline={apiOnline}
              permissions={permissions}
              onNavigate={() => setOpen(false)}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
