import { useMemo } from "react";
import FormField from "./FormField";
import Input from "./Input";
import { localIsoDate } from "../../lib/format";
import { isBackdatedDate } from "../../lib/backdateAuth";

type Props = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  hint?: string;
  disabled?: boolean;
};

export default function BusinessDateField({
  label = "Date",
  value,
  onChange,
  required = true,
  hint,
  disabled = false,
}: Props) {
  const maxDate = useMemo(() => localIsoDate(), []);
  const resolvedHint =
    hint ??
    (isBackdatedDate(value)
      ? "Past date — authorization password required on save."
      : "Defaults to today. Past dates allowed; future dates are blocked.");

  return (
    <FormField label={label} required={required} hint={resolvedHint}>
      {({ id }) => (
        <Input
          id={id}
          type="date"
          value={value}
          max={maxDate}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          required={required}
        />
      )}
    </FormField>
  );
}
