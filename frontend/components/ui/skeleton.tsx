export function SkeletonBar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-paper-200/80 ${className}`} aria-hidden />;
}

export function HeaderSkeleton() {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="w-full max-w-xl space-y-3">
        <SkeletonBar className="h-2.5 w-40" />
        <SkeletonBar className="h-7 w-3/4" />
        <SkeletonBar className="h-3 w-full" />
      </div>
      <SkeletonBar className="h-12 w-56" />
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-paper-200 px-5 py-4">
        <SkeletonBar className="h-3 w-32" />
      </div>
      <div className="divide-y divide-paper-200">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-4 px-5 py-4">
            <SkeletonBar className="h-5 w-20" />
            <SkeletonBar className="h-3 flex-1" />
            <SkeletonBar className="h-3 w-24" />
            <SkeletonBar className="h-3 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <div className="panel space-y-3 px-5 py-5">
          <SkeletonBar className="h-3 w-28" />
          <SkeletonBar className="h-8 w-48" />
          <SkeletonBar className="h-3 w-full" />
          <SkeletonBar className="h-3 w-5/6" />
        </div>
        <div className="panel space-y-3 px-5 py-5">
          <SkeletonBar className="h-3 w-32" />
          <SkeletonBar className="h-3 w-full" />
          <SkeletonBar className="h-3 w-2/3" />
        </div>
      </div>
      <div className="panel space-y-3 px-5 py-5">
        <SkeletonBar className="h-3 w-24" />
        <SkeletonBar className="h-3 w-full" />
        <SkeletonBar className="h-3 w-3/4" />
      </div>
    </div>
  );
}
