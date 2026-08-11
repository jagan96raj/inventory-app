import { Fragment, type ReactNode } from "react";
import { Dialog, Transition } from "@headlessui/react";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import IconButton from "./IconButton";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  headerIcon?: ReactNode;
  headerTone?: "default" | "accent";
  size?: "sm" | "md" | "lg" | "xl";
  children: ReactNode;
  footer?: ReactNode;
  closeOnOverlay?: boolean;
  bodyClassName?: string;
};

const sizeClass: Record<NonNullable<Props["size"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

export default function Modal({
  open,
  onClose,
  title,
  description,
  headerIcon,
  headerTone = "default",
  size = "md",
  children,
  footer,
  closeOnOverlay = true,
  bodyClassName,
}: Props) {
  return (
    <Transition show={open} as={Fragment}>
      <Dialog onClose={closeOnOverlay ? onClose : () => {}} className="relative z-[60]">
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-150"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" aria-hidden="true" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-4 sm:items-center sm:p-6">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95 translate-y-3"
              enterTo="opacity-100 scale-100 translate-y-0"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className={cn(
                  "v2-card relative flex w-full flex-col overflow-hidden shadow-lg",
                  "max-h-[min(100dvh-2rem,52rem)]",
                  sizeClass[size]
                )}
              >
                {(title || description) && (
                  <div
                    className={cn(
                      "relative flex shrink-0 items-start justify-between gap-3 border-b border-line",
                      headerTone === "accent"
                        ? "bg-gradient-to-br from-primary-500/10 via-violet-500/5 to-transparent px-5 pb-4 pt-5 dark:from-primary-500/15 dark:via-violet-500/10"
                        : "px-5 pb-3 pt-5"
                    )}
                  >
                    <div className="flex min-w-0 items-start gap-3.5">
                      {headerIcon && (
                        <div
                          className={cn(
                            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl shadow-md",
                            headerTone === "accent"
                              ? "bg-gradient-to-br from-primary-500 to-violet-500 text-white shadow-primary-500/30"
                              : "border border-line bg-surface-subtle text-primary-600 dark:text-primary-300"
                          )}
                          aria-hidden="true"
                        >
                          {headerIcon}
                        </div>
                      )}
                      <div className="min-w-0 pt-0.5">
                        {title && (
                          <Dialog.Title className="text-lg font-semibold tracking-tight text-ink">
                            {title}
                          </Dialog.Title>
                        )}
                        {description && (
                          <Dialog.Description className="mt-1 text-base leading-relaxed text-ink-muted">
                            {description}
                          </Dialog.Description>
                        )}
                      </div>
                    </div>
                    <IconButton label="Close dialog" size="sm" onClick={onClose} className="shrink-0">
                      <X />
                    </IconButton>
                  </div>
                )}

                <div
                  className={cn(
                    "min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5",
                    bodyClassName
                  )}
                >
                  {children}
                </div>

                {footer && (
                  <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-line bg-surface-subtle px-4 py-3 sm:flex-row sm:justify-end sm:px-5 [&_button]:w-full sm:[&_button]:w-auto">
                    {footer}
                  </div>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
