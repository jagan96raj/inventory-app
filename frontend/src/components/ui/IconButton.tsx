import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type Size = "sm" | "md" | "lg";

const sizeClass: Record<Size, string> = {
  sm: "h-8 w-8 rounded-lg [&_svg]:h-4 [&_svg]:w-4",
  md: "h-10 w-10 rounded-xl [&_svg]:h-5 [&_svg]:w-5",
  lg: "h-12 w-12 rounded-xl [&_svg]:h-6 [&_svg]:w-6",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  size?: Size;
  variant?: "ghost" | "outline" | "primary";
  children: ReactNode;
};

const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { label, size = "md", variant = "ghost", className, children, type = "button", ...rest },
  ref
) {
  const variantClass =
    variant === "primary"
      ? "bg-primary-600 text-white hover:bg-primary-700"
      : variant === "outline"
        ? "border border-line-strong text-ink hover:bg-surface-muted"
        : "text-ink-muted hover:text-ink hover:bg-surface-muted";
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center justify-center transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50",
        "disabled:cursor-not-allowed disabled:opacity-60",
        sizeClass[size],
        variantClass,
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

export default IconButton;
