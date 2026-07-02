import type { ReactNode } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "../../lib/cn";
import IconButton from "./IconButton";

type Tone = "info" | "success" | "warning" | "danger";

const tones: Record<Tone, { wrap: string; icon: ReactNode }> = {
  info: {
    wrap: "bg-sky-50 text-sky-900 border-sky-200 dark:bg-sky-900/20 dark:text-sky-100 dark:border-sky-800/60",
    icon: <Info />,
  },
  success: {
    wrap: "bg-accent-50 text-accent-900 border-accent-200 dark:bg-accent-900/20 dark:text-accent-100 dark:border-accent-800/60",
    icon: <CheckCircle2 />,
  },
  warning: {
    wrap: "bg-warning-50 text-warning-900 border-warning-200 dark:bg-warning-900/20 dark:text-warning-100 dark:border-warning-800/60",
    icon: <AlertTriangle />,
  },
  danger: {
    wrap: "bg-danger-50 text-danger-900 border-danger-200 dark:bg-danger-900/20 dark:text-danger-100 dark:border-danger-800/60",
    icon: <AlertCircle />,
  },
};

type Props = {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  onClose?: () => void;
  className?: string;
  actions?: ReactNode;
};

export default function Banner({ tone = "info", title, children, onClose, className, actions }: Props) {
  const t = tones[tone];
  return (
    <div
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-2xl border p-4 text-sm",
        t.wrap,
        className
      )}
    >
      <span className="mt-0.5 shrink-0 [&>svg]:h-5 [&>svg]:w-5" aria-hidden="true">
        {t.icon}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title ? "mt-1 text-current/85" : "text-current/85")}>{children}</div>}
        {actions && <div className="mt-2 flex gap-2">{actions}</div>}
      </div>
      {onClose && (
        <IconButton label="Dismiss" size="sm" onClick={onClose}>
          <X />
        </IconButton>
      )}
    </div>
  );
}
