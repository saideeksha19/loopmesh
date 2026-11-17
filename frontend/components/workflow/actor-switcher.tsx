"use client";

import { Badge } from "@/components/ui/badge";

/**
 * The Phase 2A development actor switcher is removed: the authenticated session
 * is the only source of identity. This placeholder keeps the workspace layout
 * importable until the Phase 2B session/profile UI lands.
 */
export function ActorSwitcher() {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-paper-300 bg-paper-50 px-3 py-2">
      <div className="min-w-0">
        <p className="label-mono text-[8.5px] text-ink-400">Identity</p>
        <p className="mt-1 text-[11.5px] text-ink-800">Authenticated session required</p>
      </div>
      <Badge tone="neutral" mono>
        phase 2b auth
      </Badge>
    </div>
  );
}
