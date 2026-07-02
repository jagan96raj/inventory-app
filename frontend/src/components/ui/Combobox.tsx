import { Fragment, useState, type ReactNode } from "react";
import { Combobox as HCombobox, Transition } from "@headlessui/react";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "../../lib/cn";

export type ComboOption<T> = {
  value: T;
  label: string;
  hint?: string;
};

type Props<T> = {
  value: T | null;
  onChange: (v: T | null) => void;
  options: ComboOption<T>[];
  placeholder?: string;
  emptyText?: string;
  className?: string;
  invalid?: boolean;
  renderOption?: (o: ComboOption<T>) => ReactNode;
};

export default function Combobox<T extends string | number>({
  value,
  onChange,
  options,
  placeholder = "Select…",
  emptyText = "No matches",
  className,
  invalid,
  renderOption,
}: Props<T>) {
  const [query, setQuery] = useState("");
  const filtered =
    query === ""
      ? options
      : options.filter((o) => {
          const q = query.toLowerCase();
          return (
            o.label.toLowerCase().includes(q) ||
            (o.hint?.toLowerCase().includes(q) ?? false)
          );
        });

  const selected = options.find((o) => o.value === value) ?? null;

  return (
    <HCombobox value={value} onChange={(v: T | null) => onChange(v)} nullable>
      <div className={cn("relative", className)}>
        <div
          className={cn(
            "v2-input flex items-center gap-2 pr-9",
            invalid && "border-danger-500 focus-within:border-danger-500 focus-within:ring-danger-500/30"
          )}
        >
          <HCombobox.Input
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-ink placeholder:text-ink-subtle/70 focus:outline-none focus:ring-0"
            displayValue={(v: T | null) =>
              (v != null && options.find((o) => o.value === v)?.label) || ""
            }
            placeholder={placeholder}
            onChange={(e) => setQuery(e.target.value)}
          />
          <HCombobox.Button className="absolute inset-y-0 right-0 flex items-center pr-2 text-ink-subtle">
            <ChevronsUpDown className="h-4 w-4" aria-hidden="true" />
          </HCombobox.Button>
        </div>
        <Transition
          as={Fragment}
          enter="transition ease-out duration-100"
          enterFrom="opacity-0 translate-y-1"
          enterTo="opacity-100 translate-y-0"
          leave="transition ease-in duration-75"
          leaveFrom="opacity-100 translate-y-0"
          leaveTo="opacity-0 translate-y-1"
        >
          <HCombobox.Options className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-line bg-surface py-1 shadow-lg focus:outline-none">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-sm text-ink-muted">{emptyText}</p>
            ) : (
              filtered.map((o) => (
                <HCombobox.Option
                  key={String(o.value)}
                  value={o.value}
                  className={({ active }) =>
                    cn(
                      "flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm",
                      active ? "bg-primary-50 text-ink dark:bg-primary-900/30" : "text-ink"
                    )
                  }
                >
                  {({ selected: isSelected }) => (
                    <>
                      <div className="min-w-0">
                        <p className="truncate">{renderOption ? renderOption(o) : o.label}</p>
                        {o.hint && <p className="truncate text-xs text-ink-subtle">{o.hint}</p>}
                      </div>
                      {isSelected && <Check className="h-4 w-4 text-primary-600" />}
                    </>
                  )}
                </HCombobox.Option>
              ))
            )}
          </HCombobox.Options>
        </Transition>
        {/* avoid TS unused */}
        <span className="sr-only">{selected?.label}</span>
      </div>
    </HCombobox>
  );
}
