import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ComponentType } from "react";
import { createPortal } from "react-dom";
import { NavLink, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  Banknote,
  BookOpen,
  Boxes,
  Briefcase,
  ChevronLeft,
  CircleDot,
  HandCoins,
  History,
  IndianRupee,
  LayoutDashboard,
  LogIn,
  MapPin,
  Package,
  PackageOpen,
  PackagePlus,
  ClipboardList,
  ReceiptText,
  Recycle,
  Repeat,
  Settings,
  ShoppingCart,
  Tag,
  Truck,
  Users,
  Wallet,
  Wheat,
  type LucideProps,
} from "lucide-react";
import { cn } from "../lib/cn";
import IconButton from "./ui/IconButton";
import { usePermissions, type Permission } from "../lib/permissions";

type LucideIcon = ComponentType<LucideProps>;

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  permission: Permission;
};

type NavGroup = {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
};

const NAV: NavGroup[] = [
  {
    label: "Overview",
    icon: LayoutDashboard,
    items: [{ to: "/dashboard", label: "Dashboard", icon: BarChart3, permission: "dashboard_view" }],
  },
  {
    label: "Bills",
    icon: ReceiptText,
    items: [
      { to: "/sales-bills", label: "Sales bills", icon: ShoppingCart, permission: "bills_manage" },
      { to: "/purchase-bills", label: "Purchase bills", icon: PackagePlus, permission: "bills_manage" },
      { to: "/payments", label: "Payments", icon: IndianRupee, permission: "payments_manage" },
      { to: "/customers", label: "Customers", icon: Users, permission: "masters_manage" },
    ],
  },
  {
    label: "Job work",
    icon: Briefcase,
    items: [
      { to: "/job-work", label: "Job work orders", icon: Briefcase, permission: "job_work_manage" },
      { to: "/job-work/fulfillment", label: "Job work fulfillment", icon: Truck, permission: "job_work_fulfillment_write" },
    ],
  },
  {
    label: "Inventory",
    icon: Boxes,
    items: [
      { to: "/inventory", label: "Inventory", icon: Boxes, permission: "inventory_view" },
      { to: "/fulfillment", label: "Bill fulfillment", icon: Truck, permission: "fulfillment_write" },
      { to: "/operations/processing", label: "Processing", icon: Wheat, permission: "processing_manage" },
      { to: "/operations/bag-change", label: "Bag change", icon: Repeat, permission: "bag_change_write" },
      { to: "/operations/product-transfer", label: "Transfer", icon: Truck, permission: "product_transfer_write" },
      { to: "/operations/stock-disposal", label: "Disposal", icon: Recycle, permission: "stock_disposal_write" },
    ],
  },
  {
    label: "Accounts",
    icon: Wallet,
    items: [
      { to: "/accounts", label: "Dashboard", icon: Wallet, permission: "accounts_view" },
      { to: "/accounts/cashbook", label: "Cash book", icon: BookOpen, permission: "cashbook_manage" },
      { to: "/accounts/customers", label: "Customer balances", icon: HandCoins, permission: "accounts_view" },
      { to: "/accounts/bank-accounts", label: "Accounts", icon: Banknote, permission: "bank_accounts_manage" },
      { to: "/accounts/expense-categories", label: "Expense categories", icon: ReceiptText, permission: "expense_categories_manage" },
      { to: "/accounts/setup", label: "Book settings", icon: Settings, permission: "book_settings_view" },
    ],
  },
  {
    label: "Masters",
    icon: Package,
    items: [
      { to: "/products", label: "Products", icon: Wheat, permission: "masters_manage" },
      { to: "/brands", label: "Brands", icon: Tag, permission: "masters_manage" },
      { to: "/bag-types", label: "Bag types", icon: PackageOpen, permission: "masters_manage" },
      { to: "/locations", label: "Locations", icon: MapPin, permission: "masters_manage" },
    ],
  },
  {
    label: "History",
    icon: History,
    items: [
      { to: "/histories/fulfillment", label: "Bill fulfillment", icon: History, permission: "fulfillment_view" },
      { to: "/histories/audit", label: "Audit log", icon: ClipboardList, permission: "audit_view" },
      { to: "/histories/logins", label: "Login history", icon: LogIn, permission: "audit_view" },
      { to: "/histories/bag-change", label: "Bag change", icon: History, permission: "bag_change_view" },
      { to: "/histories/product-transfer", label: "Transfer", icon: History, permission: "product_transfer_view" },
      { to: "/histories/stock-disposal", label: "Disposal", icon: History, permission: "stock_disposal_view" },
      { to: "/histories/processing", label: "Processing", icon: History, permission: "processing_view" },
    ],
  },
  {
    label: "Administration",
    icon: Settings,
    items: [{ to: "/users", label: "Users", icon: Users, permission: "users_manage" }],
  },
];

/** macOS-style rainbow hover tints on flyout rows */
const RAINBOW_HOVER = [
  "hover:bg-red-500/12 dark:hover:bg-red-400/15",
  "hover:bg-orange-500/12 dark:hover:bg-orange-400/15",
  "hover:bg-amber-500/12 dark:hover:bg-amber-400/15",
  "hover:bg-lime-500/12 dark:hover:bg-lime-400/15",
  "hover:bg-sky-500/12 dark:hover:bg-sky-400/15",
  "hover:bg-violet-500/12 dark:hover:bg-violet-400/15",
  "hover:bg-fuchsia-500/12 dark:hover:bg-fuchsia-400/15",
];

const STORAGE_KEY = "v13.sidebar.collapsed";
const APP_NAME = (import.meta.env.VITE_APP_NAME as string) || "GrainTrack";

export function useSidebarCollapsed(): [boolean, (v: boolean) => void, () => void] {
  const [collapsed, setCollapsedState] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  });
  const setCollapsed = (v: boolean) => {
    setCollapsedState(v);
    try {
      window.localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
    } catch {
      /* ignore */
    }
  };
  return [collapsed, setCollapsed, () => setCollapsed(!collapsed)];
}

type Props = {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
};

function isActivePath(pathname: string, to: string): boolean {
  if (pathname === to) return true;
  if (to !== "/" && pathname.startsWith(to + "/")) return true;
  return false;
}

function groupIsActive(group: NavGroup, pathname: string): boolean {
  return group.items.some((item) => isActivePath(pathname, item.to));
}

const NAV_ICON_SLOT = "grid h-5 w-5 shrink-0 place-items-center";

function NavBrand({ collapsed }: { collapsed: boolean }) {
  return (
    <NavLink
      to="/"
      className={cn(
        "flex h-14 shrink-0 items-center border-b border-line px-2",
        collapsed ? "justify-center" : "gap-3 px-3"
      )}
    >
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-glow">
        <Wheat className="h-5 w-5" />
      </span>
      {!collapsed && (
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold leading-tight text-ink">{APP_NAME}</p>
          <p className="truncate text-[11px] text-ink-subtle">Pulses · Millets · Cereals</p>
        </div>
      )}
    </NavLink>
  );
}

type FlyoutProps = {
  group: NavGroup;
  anchorRect: DOMRect | null;
  mobile: boolean;
  onEnter: () => void;
  onLeave: () => void;
  onNavigate: () => void;
};

function NavFlyout({ group, anchorRect, mobile, onEnter, onLeave, onNavigate }: FlyoutProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useLayoutEffect(() => {
    if (!anchorRect || !panelRef.current) return;
    const panel = panelRef.current;
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let top = anchorRect.top;
    let left = anchorRect.right + margin;

    if (mobile) {
      top = anchorRect.bottom + margin;
      left = Math.max(margin, anchorRect.left);
    } else if (left + panel.offsetWidth > vw - margin) {
      left = Math.max(margin, anchorRect.left - panel.offsetWidth - margin);
    }
    if (top + panel.offsetHeight > vh - margin) {
      top = Math.max(margin, vh - panel.offsetHeight - margin);
    }
    setPos({ top, left });
  }, [anchorRect, mobile, group.label]);

  if (!anchorRect) return null;

  return createPortal(
    <motion.div
      ref={panelRef}
      role="menu"
      aria-label={group.label}
      initial={{ opacity: 0, scale: 0.97, y: mobile ? -4 : 0, x: mobile ? 0 : -4 }}
      animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
      exit={{ opacity: 0, scale: 0.97, y: mobile ? -4 : 0, x: mobile ? 0 : -4 }}
      transition={{ duration: 0.14, ease: "easeOut" }}
      style={{ position: "fixed", top: pos.top, left: pos.left, zIndex: 70 }}
      className={cn(
        "min-w-[13.5rem] overflow-hidden rounded-xl border border-line/80 bg-surface/95 p-1.5 shadow-xl backdrop-blur-xl",
        "ring-1 ring-black/5 dark:ring-white/10"
      )}
      onMouseEnter={onEnter}
      onMouseLeave={mobile ? undefined : onLeave}
    >
      <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-ink-subtle">
        {group.label}
      </p>
      <ul className="space-y-0.5">
        {group.items.map((item, idx) => {
          const Icon = item.icon;
          return (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                role="menuitem"
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "grid grid-cols-[1.25rem_1fr] items-center gap-3 rounded-lg py-2 pl-3 pr-3 text-sm font-medium transition-colors",
                    RAINBOW_HOVER[idx % RAINBOW_HOVER.length],
                    isActive
                      ? "bg-primary-500/15 text-primary-700 dark:text-primary-200"
                      : "text-ink-muted hover:text-ink"
                  )
                }
              >
                <span className={NAV_ICON_SLOT}>
                  <Icon className="h-4 w-4 opacity-80" />
                </span>
                <span className="truncate text-left">{item.label}</span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </motion.div>,
    document.body
  );
}

type GroupButtonProps = {
  group: NavGroup;
  collapsed: boolean;
  active: boolean;
  open: boolean;
  onHover: () => void;
  onClick: () => void;
  buttonRef: (el: HTMLButtonElement | null) => void;
};

function NavGroupButton({
  group,
  collapsed,
  active,
  open,
  onHover,
  onClick,
  buttonRef,
}: GroupButtonProps) {
  const Icon = group.icon;
  return (
    <button
      ref={buttonRef}
      type="button"
      role="menuitem"
      aria-haspopup="true"
      aria-expanded={open}
      onMouseEnter={onHover}
      onClick={onClick}
      className={cn(
        "group relative grid w-full grid-cols-[1.25rem_1fr] items-center gap-3 rounded-lg py-2.5 pl-3 pr-3 text-left text-sm font-medium transition-colors",
        open || active
          ? "bg-gradient-to-r from-primary-500/18 to-transparent text-primary-700 dark:text-primary-200"
          : "text-ink-muted hover:bg-surface-muted hover:text-ink",
        collapsed && "grid-cols-1 justify-items-center px-2"
      )}
    >
      {(open || active) && (
        <span className="pointer-events-none absolute inset-y-2 left-0 w-0.5 rounded-full bg-gradient-to-b from-sky-400 via-violet-400 to-rose-400" />
      )}
      <span className={NAV_ICON_SLOT}>
        <Icon className={cn("h-4 w-4", (open || active) && "text-primary-600 dark:text-primary-300")} />
      </span>
      {!collapsed && <span className="truncate text-left leading-none">{group.label}</span>}
      {collapsed && (
        <span className="pointer-events-none absolute left-full ml-3 hidden whitespace-nowrap rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity group-hover:block group-hover:opacity-100">
          {group.label}
        </span>
      )}
    </button>
  );
}

export default function Sidebar({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onMobileClose,
}: Props) {
  const { pathname } = useLocation();
  const { can, hasRole } = usePermissions();
  const visibleNav = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => hasRole && can(item.permission)),
  })).filter((group) => group.items.length > 0);
  const [openLabel, setOpenLabel] = useState<string | null>(null);
  const [pinnedLabel, setPinnedLabel] = useState<string | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const [mobile, setMobile] = useState(false);
  const shellRef = useRef<HTMLElement>(null);
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const closeTimerRef = useRef<number | null>(null);

  const activeLabel = openLabel ?? pinnedLabel;
  const activeGroup = visibleNav.find((g) => g.label === activeLabel) ?? null;

  const cancelCloseTimer = useCallback(() => {
    if (closeTimerRef.current != null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const closeMenus = useCallback(() => {
    cancelCloseTimer();
    setOpenLabel(null);
    setPinnedLabel(null);
    setAnchorRect(null);
  }, [cancelCloseTimer]);

  const scheduleClose = useCallback(() => {
    if (pinnedLabel) return;
    cancelCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      closeMenus();
      closeTimerRef.current = null;
    }, 140);
  }, [pinnedLabel, cancelCloseTimer, closeMenus]);

  const openGroup = useCallback(
    (label: string) => {
      cancelCloseTimer();
      const btn = buttonRefs.current[label];
      if (btn) setAnchorRect(btn.getBoundingClientRect());
      setOpenLabel(label);
    },
    [cancelCloseTimer]
  );

  const handleGroupClick = (label: string) => {
    if (pinnedLabel === label) {
      closeMenus();
      return;
    }
    setPinnedLabel(label);
    openGroup(label);
  };

  useEffect(() => {
    onMobileClose();
    closeMenus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const sync = () => setMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useLayoutEffect(() => {
    if (!activeLabel) return;
    const btn = buttonRefs.current[activeLabel];
    if (btn) setAnchorRect(btn.getBoundingClientRect());
  }, [activeLabel, collapsed, mobileOpen]);

  useEffect(() => {
    if (!activeLabel) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (shellRef.current?.contains(target)) return;
      if ((target as Element).closest?.('[role="menu"]')) return;
      closeMenus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [activeLabel, closeMenus]);

  // Phone drawer always shows full labels; desktop may use collapsed icon rail.
  const chromeCollapsed = mobile ? false : collapsed;

  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.button
            type="button"
            aria-label="Close menu"
            onClick={onMobileClose}
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
        )}
      </AnimatePresence>

      <aside
        ref={shellRef}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-52 -translate-x-full flex-col border-r border-line/80 bg-surface/92 backdrop-blur-xl transition-transform duration-200",
          "lg:translate-x-0",
          chromeCollapsed ? "lg:w-[72px]" : "lg:w-52",
          mobileOpen && "translate-x-0 shadow-2xl"
        )}
        aria-label="Primary"
        onMouseLeave={() => scheduleClose()}
      >
        <NavBrand collapsed={chromeCollapsed} />
        <div className="flex-1 overflow-y-auto overscroll-contain px-2 py-3">
          <nav className="flex flex-col gap-0.5" role="menubar" aria-orientation="vertical">
            {visibleNav.map((group) => (
              <NavGroupButton
                key={group.label}
                group={group}
                collapsed={chromeCollapsed}
                active={groupIsActive(group, pathname)}
                open={activeLabel === group.label}
                onHover={() => {
                  if (pinnedLabel && pinnedLabel !== group.label) return;
                  if (pinnedLabel) return;
                  openGroup(group.label);
                }}
                onClick={() => handleGroupClick(group.label)}
                buttonRef={(el) => {
                  buttonRefs.current[group.label] = el;
                }}
              />
            ))}
            {!visibleNav.some((g) => g.items.some((i) => isActivePath(pathname, i.to))) &&
              pathname !== "/" && (
                <div className="px-3 pt-2 text-sm text-ink-subtle">
                  <CircleDot className="mr-1 inline h-3 w-3" /> Viewing {pathname}
                </div>
              )}
          </nav>
        </div>
        <div
          className={cn(
            "flex shrink-0 items-center border-t border-line px-2 py-2",
            chromeCollapsed ? "justify-center" : "justify-between gap-2"
          )}
        >
          <IconButton
            label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            size="sm"
            onClick={onToggleCollapse}
            className="hidden shrink-0 text-ink-subtle lg:inline-flex"
          >
            <ChevronLeft className={cn("transition-transform", collapsed && "rotate-180")} />
          </IconButton>
          {!chromeCollapsed && (
            <NavLink
              to="/home"
              className={cn(
                "inline-flex min-w-0 items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium text-ink-subtle hover:bg-surface-muted hover:text-ink",
                "min-h-10"
              )}
              onClick={onMobileClose}
            >
              <Settings className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">About</span>
            </NavLink>
          )}
        </div>
      </aside>

      <AnimatePresence>
        {activeGroup && activeLabel && (
          <NavFlyout
            key={activeGroup.label}
            group={activeGroup}
            anchorRect={anchorRect}
            mobile={mobile}
            onEnter={cancelCloseTimer}
            onLeave={scheduleClose}
            onNavigate={() => {
              closeMenus();
              onMobileClose();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}
