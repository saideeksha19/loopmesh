import { AlertIcon } from "@/components/icons";

export function DataUnavailable({
  title = "Live data is unavailable",
  message,
  hint,
  troubleshooting = true,
}: {
  title?: string;
  message?: string;
  hint?: string;
  /** Setup commands are useful for an offline/misconfigured API, never for a
   *  permission denial: callers rendering an authorization failure disable them. */
  troubleshooting?: boolean;
}) {
  return (
    <div className="panel tech-grid p-6 sm:p-8">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-clay-500/25 bg-clay-500/10 text-clay-500">
          <AlertIcon className="h-[18px] w-[18px]" />
        </span>
        <div>
          <h2 className="text-[15px] font-semibold text-ink-900">{title}</h2>
          <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-ink-500">
            {message ??
              "The interface is intentionally blank rather than showing invented figures. Nothing on this screen is simulated in the browser."}
          </p>
          {troubleshooting ? (
            <div className="mt-4 rounded-lg border border-paper-200 bg-paper-50 p-3 font-mono text-[11px] leading-relaxed text-ink-500">
              <p className="text-ink-400"># start the API (from the repository root)</p>
              <p className="mt-1 text-ink-700">cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000</p>
              <p className="mt-2 text-ink-400"># load demo data if the database is empty</p>
              <p className="mt-1 text-ink-700">python -m app.scripts.seed_demo</p>
            </div>
          ) : null}
          {hint ? <p className="mt-3 text-[11px] text-ink-400">{hint}</p> : null}
        </div>
      </div>
    </div>
  );
}
