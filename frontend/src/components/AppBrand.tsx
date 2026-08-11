import { cn } from "../lib/cn";

const APP_NAME = (import.meta.env.VITE_APP_NAME as string) || "GrainTrack";

/** Public path to the tractor + grain emblem (transparent PNG). */
export const APP_LOGO_MARK_SRC = "/logo-mark.png";
/** Circular grain emblem only — collapsed sidebar / compact slots. */
export const APP_LOGO_ICON_SRC = "/logo-icon.png";

type MarkProps = {
  className?: string;
  /** Accessible name; empty when adjacent text already labels the brand. */
  alt?: string;
  /** Prefer compact circular emblem (default full tractor+emblem mark). */
  compact?: boolean;
};

/** Graphic mark only (no wordmark in the file). */
export function AppLogoMark({ className, alt = "", compact = false }: MarkProps) {
  return (
    <img
      src={compact ? APP_LOGO_ICON_SRC : APP_LOGO_MARK_SRC}
      alt={alt}
      width={compact ? 162 : 315}
      height={compact ? 162 : 111}
      decoding="async"
      className={cn(
        compact
          ? "h-9 w-9 object-contain"
          : "h-8 w-auto max-w-[9rem] object-contain object-left",
        className
      )}
      draggable={false}
    />
  );
}

type BrandProps = {
  collapsed?: boolean;
  className?: string;
  showTagline?: boolean;
};

/**
 * Mark with GrainTrack label underneath (VITE_APP_NAME).
 * When `collapsed`, only the circular emblem is shown.
 */
export function AppBrand({ collapsed, className, showTagline = true }: BrandProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col",
        collapsed ? "items-center" : "items-start gap-1",
        className
      )}
    >
      <AppLogoMark
        compact={!!collapsed}
        className={collapsed ? undefined : "h-8 max-w-[8.5rem]"}
        alt={collapsed ? APP_NAME : ""}
      />
      {!collapsed && (
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold leading-tight tracking-tight text-ink">{APP_NAME}</p>
          {showTagline && (
            <p className="truncate text-[11px] text-ink-subtle">Pulses · Millets · Cereals</p>
          )}
        </div>
      )}
    </div>
  );
}

export { APP_NAME };
