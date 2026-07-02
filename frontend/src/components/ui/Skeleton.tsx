import { cn } from "../../lib/cn";

type Props = {
  className?: string;
  rounded?: "sm" | "md" | "lg" | "full";
};

export default function Skeleton({ className, rounded = "md" }: Props) {
  const radius =
    rounded === "full" ? "rounded-full" : rounded === "lg" ? "rounded-xl" : rounded === "sm" ? "rounded" : "rounded-lg";
  return <div aria-hidden="true" className={cn("v2-skeleton h-4 w-full", radius, className)} />;
}

export function SkeletonRows({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className="h-6" />
          ))}
        </div>
      ))}
    </div>
  );
}
