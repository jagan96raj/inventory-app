import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link" | "outline";
export type ButtonSize = "sm" | "md" | "lg";

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-soft hover:from-primary-600 hover:to-primary-700 active:scale-[0.98]",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-surface-muted",
  outline:
    "bg-transparent text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-700/50 hover:bg-primary-50 dark:hover:bg-primary-900/30",
  ghost: "bg-transparent text-ink hover:bg-surface-muted",
  danger:
    "bg-danger-600 text-white shadow-soft hover:bg-danger-700 active:scale-[0.98]",
  link: "bg-transparent text-primary-600 dark:text-primary-400 underline-offset-4 hover:underline px-0 py-0 h-auto",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm rounded-lg gap-1.5",
  md: "h-11 px-4 text-base rounded-xl gap-2",
  lg: "h-12 px-5 text-base rounded-xl gap-2",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  block?: boolean;
};

const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    leftIcon,
    rightIcon,
    block,
    className,
    children,
    disabled,
    type = "button",
    ...rest
  },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center font-medium transition-all",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50",
        "disabled:cursor-not-allowed disabled:opacity-60",
        variantClass[variant],
        sizeClass[size],
        block && "w-full",
        className
      )}
      {...rest}
    >
      {loading ? (
        <span
          className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
          aria-hidden="true"
        />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  );
});

export default Button;
