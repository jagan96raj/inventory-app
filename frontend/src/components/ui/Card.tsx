import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = HTMLAttributes<HTMLDivElement> & {
  variant?: "default" | "subtle" | "glass" | "elevated";
  interactive?: boolean;
};

export const Card = forwardRef<HTMLDivElement, Props>(function Card(
  { className, variant = "default", interactive, ...rest },
  ref
) {
  const variantClass =
    variant === "subtle"
      ? "bg-surface-subtle/90 border-line"
      : variant === "glass"
        ? "v2-glass border-line/60"
        : variant === "elevated"
          ? "v2-card border-line shadow-lg"
          : "v2-card";
  return (
    <div
      ref={ref}
      className={cn(
        "rounded-2xl border",
        variantClass,
        interactive && "transition-all hover:shadow-lg hover:-translate-y-0.5",
        className
      )}
      {...rest}
    />
  );
});

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-5", className)}>
      <div className="min-w-0">
        {title && <h3 className="text-lg font-semibold tracking-tight text-primary-900 dark:text-primary-100">{title}</h3>}
        {subtitle && <p className="mt-1 text-base text-indigo-700/80 dark:text-indigo-200/80">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <div className={cn("p-5", className)}>{children}</div>;
}

export function CardFooter({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("flex items-center justify-end gap-2 border-t border-line px-5 py-3", className)}>
      {children}
    </div>
  );
}

export default Card;
