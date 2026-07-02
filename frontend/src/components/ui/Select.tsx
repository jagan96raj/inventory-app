import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

type Props = SelectHTMLAttributes<HTMLSelectElement> & {
  invalid?: boolean;
};

const Select = forwardRef<HTMLSelectElement, Props>(function Select(
  { className, invalid, children, ...rest },
  ref
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "v2-input pr-9 appearance-none bg-no-repeat bg-[length:14px_14px] bg-[right_0.75rem_center]",
        "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><path fill=%22none%22 stroke=%22%23666%22 stroke-width=%221.75%22 stroke-linecap=%22round%22 d=%22M4 6l4 4 4-4%22/></svg>')]",
        invalid && "border-danger-500 focus:border-danger-500 focus:ring-danger-500/30",
        className
      )}
      {...rest}
    >
      {children}
    </select>
  );
});

export default Select;
