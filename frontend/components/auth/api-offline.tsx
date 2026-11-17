import { LoopMark } from "@/components/icons";

/**
 * Shown when the workspace cannot reach the API at all. This is deliberately
 * distinct from a sign-out: an unreachable backend must never bounce the user
 * to the login screen or discard their session.
 */
export function ApiOffline({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper-100 px-6">
      <div className="panel w-full max-w-md p-7 text-center">
        <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-forest-900 text-lime-400">
          <LoopMark className="h-6 w-6" />
        </span>
        <p className="label-mono mt-5 text-[9px] text-ink-400">Workspace unavailable</p>
        <h1 className="mt-2 text-[19px] font-semibold tracking-[-0.01em] text-ink-900">
          The LOOPMESH API is not reachable
        </h1>
        <p className="mt-2 text-[12.5px] leading-relaxed text-ink-500">{message}</p>
        <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-400">
          Start the backend on port 8000, then retry
        </p>
        <a
          href="/overview"
          className="mt-5 inline-flex h-9 items-center justify-center rounded-lg bg-forest-900 px-4 text-[12px] font-medium text-lime-300 transition-colors hover:bg-forest-800"
        >
          Retry
        </a>
      </div>
    </div>
  );
}
