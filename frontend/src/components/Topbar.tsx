import { Fragment, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Menu, Transition } from "@headlessui/react";
import {
  ChevronRight,
  Command,
  LogOut,
  Menu as MenuIcon,
  Moon,
  Rows2,
  Rows3,
  Search,
  Settings,
  Sun,
  SunMoon,
  User as UserIcon,
} from "lucide-react";
import { cn } from "../lib/cn";
import { useTheme } from "../lib/theme";
import { useDensity } from "../lib/density";
import { useAuth } from "../context/AuthContext";
import { ROLE_LABELS } from "../lib/permissions";
import IconButton from "./ui/IconButton";

type Props = {
  onOpenSidebar: () => void;
  onOpenPalette: () => void;
};

const TITLE_MAP: Record<string, string> = {
  "/": "Dashboard",
  "/dashboard": "Dashboard",
  "/home": "Welcome",
  "/profile": "Profile",
  "/products": "Products",
  "/brands": "Brands",
  "/bag-types": "Bag types",
  "/locations": "Locations",
  "/inventory": "Inventory",
  "/customers": "Customers",
  "/sales-bills": "Sales bills",
  "/purchase-bills": "Purchase bills",
  "/fulfillment": "Fulfillment",
  "/operations/processing": "Processing",
  "/operations/bag-change": "Bag change",
  "/operations/product-transfer": "Product transfer",
  "/operations/stock-disposal": "Stock disposal",
  "/payments": "Payments",
  "/payments/new": "Record payment",
  "/histories/bag-change": "Bag-change history",
  "/histories/product-transfer": "Transfer history",
  "/histories/stock-disposal": "Disposal history",
  "/accounts": "Accounts dashboard",
  "/accounts/cashbook": "Cash book",
  "/accounts/cashbook/new": "New cash-book entry",
  "/accounts/customers": "Customer balances",
  "/accounts/bank-accounts": "Accounts",
  "/accounts/expense-categories": "Expense categories",
  "/accounts/setup": "Book settings",
  "/histories/processing": "Processing history",
};

function deriveTitle(pathname: string): string {
  if (TITLE_MAP[pathname]) return TITLE_MAP[pathname];
  if (pathname.startsWith("/sales-bills")) {
    if (pathname.endsWith("/edit")) return "Edit sales bill";
    if (pathname.endsWith("/new")) return "New sales bill";
    if (pathname.endsWith("/payment")) return "Record payment";
    return "Sales bill";
  }
  if (pathname.startsWith("/purchase-bills")) {
    if (pathname.endsWith("/edit")) return "Edit purchase bill";
    if (pathname.endsWith("/new")) return "New purchase bill";
    if (pathname.endsWith("/payment")) return "Record payment";
    return "Purchase bill";
  }
  if (pathname.startsWith("/operations/processing/")) return "Processing job";
  if (pathname.startsWith("/fulfillment/deliver/")) return "Deliver";
  if (pathname.startsWith("/fulfillment/return/")) return "Return";
  return "GrainTrack";
}

function ThemeToggle({ className }: { className?: string }) {
  const { resolved, mode, setMode } = useTheme();
  const cycle = () => {
    const next: "light" | "dark" | "system" =
      mode === "light" ? "dark" : mode === "dark" ? "system" : "light";
    setMode(next);
  };
  const Icon = mode === "system" ? SunMoon : resolved === "dark" ? Sun : Moon;
  const modeLabel = mode === "system" ? "System" : mode === "dark" ? "Dark" : "Light";
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={`Theme: ${modeLabel} (click to change)`}
      title={`Theme: ${modeLabel} (click to change)`}
      className={cn(
        "inline-flex h-9 min-h-9 items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 text-sm font-medium text-ink-muted transition-colors",
        "hover:bg-surface-subtle hover:text-ink",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50",
        className
      )}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span className="hidden sm:inline">{modeLabel}</span>
      <span className="sr-only sm:hidden">{modeLabel}</span>
    </button>
  );
}

function DensityToggle({ className }: { className?: string }) {
  const { density, toggle } = useDensity();
  const compact = density === "compact";
  const Icon = compact ? Rows2 : Rows3;
  const label = compact ? "Compact spacing (click for comfortable)" : "Comfortable spacing (click for compact)";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 min-h-9 items-center gap-1.5 rounded-xl border px-2.5 text-sm font-medium transition-colors",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50",
        compact
          ? "border-primary-200 bg-primary-50 text-primary-700 dark:border-primary-800/50 dark:bg-primary-900/30 dark:text-primary-200"
          : "border-line bg-surface text-ink-muted hover:bg-surface-subtle hover:text-ink",
        className
      )}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
      <span className="hidden sm:inline">{compact ? "Compact" : "Comfortable"}</span>
      <span className="sr-only sm:hidden">{compact ? "Compact" : "Comfortable"}</span>
    </button>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { resolved, mode, setMode } = useTheme();
  const { density, toggle: toggleDensity } = useDensity();
  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };
  const cycleTheme = () => {
    const next: "light" | "dark" | "system" =
      mode === "light" ? "dark" : mode === "dark" ? "system" : "light";
    setMode(next);
  };
  const themeLabel = mode === "system" ? "System" : mode === "dark" ? "Dark" : "Light";
  const ThemeIcon = mode === "system" ? SunMoon : resolved === "dark" ? Sun : Moon;
  const compact = density === "compact";
  return (
    <Menu as="div" className="relative">
      <Menu.Button as={Fragment}>
        <button
          type="button"
          className={cn(
            "flex h-10 min-h-10 items-center gap-2 rounded-full border border-line bg-surface pl-1 pr-2.5 transition-shadow hover:shadow-soft sm:pr-3",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50"
          )}
          aria-label="User menu"
        >
          {user?.picture_url ? (
            <img src={user.picture_url} alt="" className="h-7 w-7 rounded-full" />
          ) : (
            <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-xs font-semibold text-white">
              {(user?.name || user?.email || "?").charAt(0).toUpperCase()}
            </span>
          )}
          <span className="hidden max-w-[10rem] truncate text-xs font-medium text-ink md:inline">
            {user?.name || user?.email || "Account"}
          </span>
        </button>
      </Menu.Button>
      <Transition
        as={Fragment}
        enter="transition ease-out duration-100"
        enterFrom="opacity-0 scale-95"
        enterTo="opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="opacity-100 scale-100"
        leaveTo="opacity-0 scale-95"
      >
        <Menu.Items className="absolute right-0 z-50 mt-2 w-64 origin-top-right overflow-hidden rounded-xl border border-line bg-surface shadow-lg focus:outline-none">
          <div className="border-b border-line px-3 py-3">
            <p className="truncate text-sm font-semibold text-ink">{user?.name || "Signed in"}</p>
            <p className="truncate text-xs text-ink-muted">{user?.email}</p>
            {user?.company_name && (
              <p className="truncate text-xs text-ink-subtle">{user.company_name}</p>
            )}
            {user?.role && (
              <p className="truncate text-xs text-primary-700 dark:text-primary-300">{ROLE_LABELS[user.role]}</p>
            )}
          </div>
          <div className="border-b border-line py-1 md:hidden">
            <Menu.Item>
              {({ active }) => (
                <button
                  type="button"
                  onClick={cycleTheme}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2.5 text-sm",
                    active && "bg-surface-muted"
                  )}
                >
                  <ThemeIcon className="h-4 w-4" /> Theme: {themeLabel}
                </button>
              )}
            </Menu.Item>
            <Menu.Item>
              {({ active }) => (
                <button
                  type="button"
                  onClick={toggleDensity}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2.5 text-sm",
                    active && "bg-surface-muted"
                  )}
                >
                  {compact ? <Rows2 className="h-4 w-4" /> : <Rows3 className="h-4 w-4" />}
                  {compact ? "Compact spacing" : "Comfortable spacing"}
                </button>
              )}
            </Menu.Item>
          </div>
          <Menu.Item>
            {({ active }) => (
              <Link
                to="/profile"
                className={cn(
                  "flex items-center gap-2 px-3 py-2.5 text-sm",
                  active && "bg-surface-muted"
                )}
              >
                <UserIcon className="h-4 w-4" /> Profile
              </Link>
            )}
          </Menu.Item>
          <Menu.Item>
            {({ active }) => (
              <Link
                to="/inventory"
                className={cn(
                  "flex items-center gap-2 px-3 py-2.5 text-sm",
                  active && "bg-surface-muted"
                )}
              >
                <Settings className="h-4 w-4" /> Workspace
              </Link>
            )}
          </Menu.Item>
          <Menu.Item>
            {({ active }) => (
              <button
                type="button"
                onClick={() => void handleLogout()}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-2.5 text-sm text-danger-600",
                  active && "bg-danger-50 dark:bg-danger-900/30"
                )}
              >
                <LogOut className="h-4 w-4" /> Sign out
              </button>
            )}
          </Menu.Item>
        </Menu.Items>
      </Transition>
    </Menu>
  );
}

export default function Topbar({ onOpenSidebar, onOpenPalette }: Props) {
  const { pathname } = useLocation();
  const title = deriveTitle(pathname);

  // Cmd/Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        onOpenPalette();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onOpenPalette]);

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line v2-glass px-4 sm:px-6"
      )}
    >
      <IconButton label="Open menu" size="sm" onClick={onOpenSidebar} className="lg:hidden">
        <MenuIcon />
      </IconButton>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
          <span>GrainTrack</span>
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
          <span className="truncate text-ink-muted">{title}</span>
        </div>
        <h2 className="truncate text-base font-semibold text-ink">{title}</h2>
      </div>
      <button
        type="button"
        onClick={onOpenPalette}
        className={cn(
          "hidden h-10 items-center gap-2 rounded-xl border border-line bg-surface px-3 text-base text-ink-muted shadow-soft transition-colors",
          "hover:text-ink hover:bg-surface-subtle md:inline-flex",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50"
        )}
      >
        <Search className="h-4 w-4" />
        <span>Search</span>
        <kbd className="ml-2 inline-flex items-center gap-1 rounded border border-line bg-surface-muted px-1.5 py-0.5 v2-mono text-[10px]">
          <Command className="h-3 w-3" /> K
        </kbd>
      </button>
      <IconButton label="Search (Cmd/Ctrl+K)" size="sm" onClick={onOpenPalette} className="md:hidden">
        <Search />
      </IconButton>
      <DensityToggle className="hidden md:inline-flex" />
      <ThemeToggle className="hidden md:inline-flex" />
      <UserMenu />
    </header>
  );
}
