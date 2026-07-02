import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  invalid?: boolean;
};

const Textarea = forwardRef<HTMLTextAreaElement, Props>(function Textarea(
  { className, invalid, ...rest },
  ref
) {
  return (
    <textarea
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-xl border bg-surface px-3 py-2 text-base text-ink",
        "placeholder:text-ink-subtle/70 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/30",
        "disabled:opacity-60",
        invalid
          ? "border-danger-500 focus:border-danger-500 focus:ring-danger-500/30"
          : "border-line-strong",
        className
      )}
      {...rest}
    />
  );
});

export default Textarea;
