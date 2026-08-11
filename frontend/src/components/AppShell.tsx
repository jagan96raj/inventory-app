import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "../lib/cn";
import Sidebar, { useSidebarCollapsed } from "./Sidebar";
import Topbar from "./Topbar";
import CommandPalette from "./CommandPalette";
import AppAmbientBackground from "./AppAmbientBackground";
import { toast } from "./ui/Toaster";

export default function AppShell() {
  const { pathname } = useLocation();
  const isProcessingJobPage = /^\/operations\/processing\/[^/]+$/.test(pathname);
  const [collapsed, , toggleCollapsed] = useSidebarCollapsed();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    document.body.classList.add("app-shell-v2");
    return () => document.body.classList.remove("app-shell-v2");
  }, []);

  useEffect(() => {
    const onForbidden = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      toast.error(detail || "You do not have permission for this action.");
    };
    window.addEventListener("app:forbidden", onForbidden as EventListener);
    return () => window.removeEventListener("app:forbidden", onForbidden as EventListener);
  }, []);

  // Escape closes palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  return (
    <div className="v2-app-canvas min-h-screen text-ink">
      <AppAmbientBackground variant="app" />
      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={toggleCollapsed}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />
      <div
        className={cn(
          "relative z-[1] flex min-h-screen flex-col transition-[padding] duration-200",
          collapsed ? "lg:pl-[72px]" : "lg:pl-52"
        )}
      >
        <Topbar
          onOpenSidebar={() => setMobileOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className={cn("mx-auto w-full min-w-0", isProcessingJobPage ? "max-w-none" : "max-w-7xl")}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
