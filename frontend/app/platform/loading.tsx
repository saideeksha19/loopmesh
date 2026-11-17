export default function PlatformLoading() {
  return (
    <div aria-busy="true" aria-live="polite" className="space-y-4">
      <span className="sr-only">Loading platform data</span>
      <div className="h-16 animate-pulse rounded-xl border border-paper-200 bg-paper-100/70" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div
            key={index}
            className="h-24 animate-pulse rounded-xl border border-paper-200 bg-paper-100/70"
          />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl border border-paper-200 bg-paper-100/70" />
    </div>
  );
}
