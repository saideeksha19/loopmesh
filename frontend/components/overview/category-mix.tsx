import Link from "next/link";

import { categoryTone, formatNumber, titleCase } from "@/lib/format";

export function CategoryMix({
  categories,
  total,
}: {
  categories: { key: string; count: number }[];
  total: number;
}) {
  const max = Math.max(1, ...categories.map((item) => item.count));

  return (
    <div className="px-5 py-4 sm:px-6">
      <ul className="space-y-3.5">
        {categories.slice(0, 6).map((category, idx) => (
          <li key={category.key} className="animate-rise" style={{ animationDelay: `${idx * 35}ms` }}>
            <div className="mb-1.5 flex items-baseline justify-between">
              <Link
                href={`/materials?category=${category.key}`}
                className="text-[12px] font-medium text-ink-700 transition-premium hover:text-forest-700"
              >
                {titleCase(category.key)}
              </Link>
              <span className="figure text-[11px] text-ink-500">{category.count}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full border border-paper-300/40 bg-paper-100/80">
              <div
                className={`h-full rounded-full transition-all duration-700 ease-out ${categoryTone(category.key)}`}
                style={{ width: `${Math.round((category.count / max) * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      <p className="mt-4 border-t border-paper-200/80 pt-3 text-[10.5px] text-ink-400">
        {formatNumber(total)} streams across {categories.length} material categories.
      </p>
    </div>
  );
}
