import { Children, isValidElement, useState, type ReactElement, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type TabProps = {
  id: string;
  label: ReactNode;
  children: ReactNode;
  badge?: ReactNode;
};

export function Tab(_: TabProps): null {
  return null;
}

type Props = {
  defaultId?: string;
  value?: string;
  onChange?: (id: string) => void;
  className?: string;
  variant?: "underline" | "pill";
  size?: "md" | "lg" | "xl";
  children: ReactNode;
};

export default function Tabs({
  defaultId,
  value,
  onChange,
  className,
  variant = "underline",
  size = "lg",
  children,
}: Props) {
  const items: ReactElement<TabProps>[] = Children.toArray(children).filter(
    (c): c is ReactElement<TabProps> => isValidElement(c)
  );
  const fallbackId = items[0]?.props.id;
  const [internal, setInternal] = useState<string | undefined>(defaultId ?? fallbackId);
  const active = value ?? internal ?? fallbackId;
  const setActive = (id: string) => {
    if (onChange) onChange(id);
    else setInternal(id);
  };

  return (
    <div className={className}>
      <div
        role="tablist"
        className={cn(
          variant === "underline"
            ? cn(
                "flex flex-wrap gap-1.5 border-b border-line/80",
                size === "xl" ? "gap-3" : size === "lg" ? "gap-2.5" : "gap-1"
              )
            : cn(
                "inline-flex w-full flex-wrap items-stretch gap-2 rounded-2xl border border-line/80 bg-surface-muted/80",
                size === "xl" ? "gap-2.5 p-2.5" : size === "lg" ? "p-2" : "gap-1.5 p-1.5"
              )
        )}
      >
        {items.map((tab) => {
          const isActive = tab.props.id === active;
          return (
            <button
              key={tab.props.id}
              role="tab"
              aria-selected={isActive}
              type="button"
              onClick={() => setActive(tab.props.id)}
              className={cn(
                "inline-flex items-center gap-2 whitespace-nowrap font-semibold transition-all",
                "outline-none focus-visible:ring-2 focus-visible:ring-primary-500/35 focus-visible:ring-offset-1 focus-visible:ring-offset-surface",
                size === "xl" ? "text-lg" : size === "lg" ? "text-base" : "text-sm",
                variant === "underline"
                  ? cn(
                      size === "xl"
                        ? "h-16 border-b-[3px] px-6"
                        : size === "lg"
                          ? "h-14 border-b-[3px] px-5"
                          : "h-11 border-b-2 px-4",
                      isActive
                        ? "border-primary-500 text-primary-800 dark:text-primary-200"
                        : "border-transparent text-ink-muted hover:text-ink"
                    )
                  : cn(
                      "flex-1 justify-center rounded-xl sm:flex-none",
                      size === "xl"
                        ? "min-h-[4rem] px-6 py-3.5"
                        : size === "lg"
                          ? "min-h-[3.25rem] px-5 py-3"
                          : "min-h-[2.75rem] px-4 py-2.5",
                      isActive
                        ? "bg-surface text-ink shadow-soft ring-1 ring-line/70"
                        : "text-ink-muted hover:bg-surface/70 hover:text-ink"
                    )
              )}
            >
              {tab.props.label}
              {tab.props.badge != null && tab.props.badge !== false && (
                <span
                  className={cn(
                    "rounded-full font-semibold tabular-nums",
                    size === "xl"
                      ? "min-w-[2rem] px-3 py-0.5 text-base leading-5"
                      : size === "lg"
                        ? "min-w-[1.75rem] px-2.5 py-0.5 text-sm leading-5"
                        : "min-w-[1.5rem] px-2 py-0.5 text-xs leading-4",
                    isActive
                      ? "bg-primary-100 text-primary-800 dark:bg-primary-900/60 dark:text-primary-100"
                      : "bg-surface-subtle text-ink-muted"
                  )}
                >
                  {tab.props.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className={cn(size === "xl" ? "pt-7" : size === "lg" ? "pt-6" : "pt-5")}>
        {items.map((tab) =>
          tab.props.id === active ? (
            <div key={tab.props.id} role="tabpanel">
              {tab.props.children}
            </div>
          ) : null
        )}
      </div>
    </div>
  );
}
