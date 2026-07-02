import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  leftIcon?: ReactNode;
  rightSlot?: ReactNode;
  invalid?: boolean;
  inputClassName?: string;
};

const Input = forwardRef<HTMLInputElement, Props>(function Input(
  { leftIcon, rightSlot, invalid, className, inputClassName, ...rest },
  ref
) {
  return (
    <div
      className={cn(
        "v2-input flex items-center gap-2 px-3",
        invalid && "border-danger-500 focus-within:ring-danger-500/30 focus-within:border-danger-500",
        className
      )}
    >
      {leftIcon && (
        <span className="text-ink-subtle shrink-0 [&>svg]:h-4 [&>svg]:w-4" aria-hidden="true">
          {leftIcon}
        </span>
      )}
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-ink placeholder:text-ink-subtle/70",
          "focus:outline-none focus:ring-0",
          inputClassName
        )}
        {...rest}
      />
      {rightSlot && <span className="shrink-0 text-ink-subtle">{rightSlot}</span>}
    </div>
  );
});

export default Input;
