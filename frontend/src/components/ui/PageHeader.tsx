import { Fragment, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "../../lib/cn";

type Crumb = { to?: string; label: string };

type Props = {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
  eyebrow?: ReactNode;
  className?: string;
};

function deriveCrumbs(pathname: string): Crumb[] {
  const parts = pathname.split("/").filter(Boolean);
  const out: Crumb[] = [];
  let acc = "";
  for (const p of parts) {
    acc += "/" + p;
    out.push({ to: acc, label: decodeURIComponent(p).replace(/-/g, " ") });
  }
  return out;
}

export default function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
  eyebrow,
  className,
}: Props) {
  const { pathname } = useLocation();
  const crumbs = breadcrumbs ?? deriveCrumbs(pathname);
  return (
    <header className={cn("mb-6 flex flex-col gap-3", className)}>
      <nav aria-label="Breadcrumb" className="flex items-center text-sm text-primary-700/80 dark:text-primary-300/80">
        <Link to="/" className="inline-flex items-center gap-1 hover:text-primary-700 dark:hover:text-primary-200">
          <Home className="h-3.5 w-3.5" />
          <span className="sr-only">Home</span>
        </Link>
        {crumbs.map((c, i) => (
          <Fragment key={`${c.label}-${i}`}>
            <ChevronRight className="mx-1 h-3.5 w-3.5 opacity-60" aria-hidden="true" />
            {c.to && i < crumbs.length - 1 ? (
              <Link to={c.to} className="capitalize hover:text-primary-700 dark:hover:text-primary-200">
                {c.label}
              </Link>
            ) : (
              <span className="capitalize font-medium text-primary-800 dark:text-primary-200">{c.label}</span>
            )}
          </Fragment>
        ))}
      </nav>
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-1 text-sm font-medium uppercase tracking-wider text-primary-600 dark:text-primary-300">
              {eyebrow}
            </p>
          )}
          <h1 className="truncate bg-gradient-to-r from-primary-900 via-primary-700 to-primary-600 bg-clip-text text-xl font-bold tracking-tight text-transparent sm:text-2xl dark:from-primary-100 dark:via-primary-200 dark:to-primary-100">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1 text-sm text-primary-800/85 sm:max-w-2xl dark:text-primary-200/85">{subtitle}</p>
          )}
        </div>
        {actions && (
          <div className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto sm:justify-end [&_a]:w-full [&_a]:sm:w-auto [&_button]:w-full [&_button]:sm:w-auto">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}
