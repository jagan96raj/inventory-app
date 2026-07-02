import { forwardRef, type InputHTMLAttributes } from "react";
import Input from "./Input";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
  suffix?: string;
};

const NumberInput = forwardRef<HTMLInputElement, Props>(function NumberInput(
  { suffix, ...rest },
  ref
) {
  return (
    <Input
      ref={ref}
      type="number"
      inputMode="decimal"
      onWheel={(e) => e.currentTarget.blur()}
      rightSlot={suffix ? <span className="text-xs font-medium text-ink-subtle">{suffix}</span> : undefined}
      inputClassName="text-right v2-mono"
      {...rest}
    />
  );
});

export default NumberInput;
