import { useId, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  htmlFor?: string;
  className?: string;
  layout?: "vertical" | "horizontal";
  children: ReactNode | ((props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode);
};

export default function FormField({
  label,
  hint,
  error,
  required,
  htmlFor,
  className,
  layout = "vertical",
  children,
}: Props) {
  const autoId = useId();
  const id = htmlFor ?? autoId;
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  const horizontal = layout === "horizontal";

  const labelEl = label ? (
    <label
      htmlFor={id}
      className={cn(
        "text-sm font-medium text-ink-muted",
        horizontal ? "sm:pt-2.5 sm:text-right" : "mb-1.5 flex items-center gap-1.5"
      )}
    >
      <span className={cn(horizontal && "inline-flex items-center justify-end gap-1.5")}>
        <span>{label}</span>
        {required && (
          <span className="text-xs font-normal normal-case tracking-normal text-ink-subtle" aria-hidden="true">
            (required)
          </span>
        )}
      </span>
    </label>
  ) : null;

  const control = typeof children === "function"
    ? children({ id, "aria-describedby": describedBy, "aria-invalid": !!error })
    : children;

  const meta = error ? (
    <p id={`${id}-err`} className="v2-error">
      {error}
    </p>
  ) : hint ? (
    <p id={`${id}-hint`} className="v2-hint">
      {hint}
    </p>
  ) : null;

  if (horizontal) {
    return (
      <div
        className={cn(
          "grid grid-cols-1 gap-1 sm:grid-cols-[5.5rem_minmax(0,1fr)] sm:gap-x-4 sm:gap-y-1",
          className
        )}
      >
        {labelEl}
        <div className="min-w-0">{control}</div>
        {meta && <div className="sm:col-start-2">{meta}</div>}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", className)}>
      {labelEl}
      {control}
      {meta}
    </div>
  );
}
