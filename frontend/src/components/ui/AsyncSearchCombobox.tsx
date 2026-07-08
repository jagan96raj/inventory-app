import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Combobox as HCombobox, Transition } from "@headlessui/react";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";
import type { ComboOption } from "./Combobox";

type Props = {
  value: number | null;
  onChange: (value: number | null, option?: ComboOption<number>) => void;
  searchFn: (query: string) => Promise<ComboOption<number>[]>;
  placeholder?: string;
  emptyText?: string;
  typeHint?: string;
  initialLabel?: string;
  className?: string;
  invalid?: boolean;
  disabled?: boolean;
  minChars?: number;
  debounceMs?: number;
  renderOption?: (o: ComboOption<number>) => ReactNode;
};

export default function AsyncSearchCombobox({
  value,
  onChange,
  searchFn,
  placeholder = "Type to search…",
  emptyText = "No matches",
  typeHint = "Type at least 1 character to search",
  initialLabel,
  className,
  invalid,
  disabled,
  minChars = 1,
  debounceMs = 250,
  renderOption,
}: Props) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<ComboOption<number>[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState(initialLabel ?? "");
  const requestId = useRef(0);

  useEffect(() => {
    if (initialLabel) setSelectedLabel(initialLabel);
  }, [initialLabel]);

  useEffect(() => {
    if (value == null) {
      setSelectedLabel("");
      return;
    }
    const match = options.find((o) => o.value === value);
    if (match) setSelectedLabel(match.label);
    else if (initialLabel) setSelectedLabel(initialLabel);
  }, [value, options, initialLabel]);

  const runSearch = useCallback(
    async (q: string, opts?: { allowEmpty?: boolean }) => {
      const trimmed = q.trim();
      if (!opts?.allowEmpty && trimmed.length < minChars) {
        setOptions([]);
        setLoading(false);
        return;
      }
      const id = ++requestId.current;
      setLoading(true);
      try {
        const rows = await searchFn(trimmed);
        if (id === requestId.current) setOptions(rows);
      } catch {
        if (id === requestId.current) setOptions([]);
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [minChars, searchFn]
  );

  useEffect(() => {
    if (disabled) return;
    const trimmed = query.trim();
    if (trimmed.length === 0) {
      setLoading(false);
      return;
    }
    if (trimmed.length < minChars) {
      setOptions([]);
      setLoading(false);
      return;
    }
    const timer = window.setTimeout(() => {
      void runSearch(trimmed);
    }, debounceMs);
    return () => window.clearTimeout(timer);
  }, [query, debounceMs, minChars, runSearch, disabled]);

  const displayLabel =
    value != null
      ? options.find((o) => o.value === value)?.label || selectedLabel
      : "";

  const showBrowseHint = query.trim().length === 0 && options.length > 0 && !loading;
  const listEmptyText =
    loading
      ? "Searching…"
      : query.trim().length === 0
        ? emptyText
        : query.trim().length < minChars
          ? typeHint
          : emptyText;

  const triggerBrowse = useCallback(() => {
    if (disabled) return;
    if (query.trim().length > 0) return;
    if (loading) return;
    void runSearch("", { allowEmpty: true });
  }, [disabled, loading, query, runSearch]);

  return (
    <HCombobox
      value={value}
      onChange={(v: number | null) => {
        const opt = options.find((o) => o.value === v);
        if (opt) setSelectedLabel(opt.label);
        onChange(v, opt);
        setQuery("");
      }}
      nullable
      disabled={disabled}
    >
      <div className={cn("relative", className)}>
            <div
              className={cn(
                "v2-input flex items-center gap-2 pr-9",
                invalid && "border-danger-500 focus-within:border-danger-500 focus-within:ring-danger-500/30",
                disabled && "cursor-not-allowed opacity-60"
              )}
            >
              <HCombobox.Input
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-base text-ink placeholder:text-ink-subtle/70 focus:outline-none focus:ring-0 disabled:cursor-not-allowed"
                displayValue={() => displayLabel}
                placeholder={placeholder}
                onChange={(e) => {
                  setQuery(e.target.value);
                }}
                onFocus={triggerBrowse}
                disabled={disabled}
              />
              <HCombobox.Button
                className="absolute inset-y-0 right-0 flex items-center pr-2 text-ink-subtle"
                onClick={triggerBrowse}
                disabled={disabled}
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <ChevronsUpDown className="h-4 w-4" aria-hidden="true" />
                )}
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
                {showBrowseHint && (
                  <p className="border-b border-line/70 px-3 py-2 text-xs font-medium text-ink-muted">
                    Showing first {options.length} — type to filter
                  </p>
                )}
                {options.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-ink-muted">{listEmptyText}</p>
                ) : (
                  options.map((o) => (
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
          </div>
    </HCombobox>
  );
}
