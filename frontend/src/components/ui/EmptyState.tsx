import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
};

export default function EmptyState({ icon, title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-line bg-surface-subtle px-6 py-12 text-center",
        className
      )}
    >
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 [&>svg]:h-6 [&>svg]:w-6">
          {icon}
        </div>
      )}
      <div className="space-y-1">
        <p className="text-base font-semibold text-ink">{title}</p>
        {description && <p className="text-base text-ink-muted">{description}</p>}
      </div>
      {action && <div className="mt-1 w-full max-w-xs [&_a]:block [&_a]:w-full [&_button]:w-full">{action}</div>}
    </div>
  );
}
