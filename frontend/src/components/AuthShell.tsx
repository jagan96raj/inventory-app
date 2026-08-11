import { useEffect, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Wheat } from "lucide-react";
import { cn } from "../lib/cn";
import AppAmbientBackground from "./AppAmbientBackground";

type Props = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Wider form column for multi-section pages (e.g. company register). */
  wide?: boolean;
};

const ROTATING = [
  {
    title: "Manage stock by location",
    body: "Bags, loose kg, totals — always reconciled against bills and operations.",
  },
  {
    title: "Bill, deliver, settle",
    body: "Sales and purchase bills with set-off payments and void with cascade.",
  },
  {
    title: "Processing, transfer, dispose",
    body: "Mass-balanced processing jobs with v9.3 tolerance and reprocess guards.",
  },
];

const APP_NAME = (import.meta.env.VITE_APP_NAME as string) || "GrainTrack";

export default function AuthShell({ title, subtitle, children, footer, wide }: Props) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setIdx((i) => (i + 1) % ROTATING.length), 4200);
    return () => clearInterval(id);
  }, []);
  const current = ROTATING[idx];

  return (
    <div className="v2-auth-canvas grid min-h-svh min-h-screen grid-cols-1 text-ink lg:grid-cols-[1.05fr_1fr]">
      {/* Hero */}
      <section className="relative hidden overflow-hidden bg-gradient-to-br from-primary-700 via-primary-600 to-primary-500 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <AppAmbientBackground variant="auth" />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary-700/88 via-primary-600/82 to-primary-500/78"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-white/10 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-40 right-0 h-[28rem] w-[28rem] rounded-full bg-accent-400/30 blur-3xl"
        />
        <header className="relative z-[1] flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 backdrop-blur">
            <Wheat className="h-5 w-5" />
          </span>
          <div>
            <p className="text-lg font-semibold tracking-tight">{APP_NAME}</p>
            <p className="text-xs text-white/70">Pulses · Millets · Cereals</p>
          </div>
        </header>
        <div className="relative z-[1] max-w-md">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-white/70">
            v13.0 · Modern operations
          </p>
          <motion.h1
            key={current.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="text-3xl font-semibold leading-tight"
          >
            {current.title}
          </motion.h1>
          <motion.p
            key={current.body}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.05 }}
            className="mt-3 max-w-md text-white/85"
          >
            {current.body}
          </motion.p>
          <div className="mt-6 flex gap-2">
            {ROTATING.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 w-8 rounded-full transition-all ${i === idx ? "bg-white" : "bg-white/30"}`}
              />
            ))}
          </div>
        </div>
        <footer className="relative z-[1] text-xs text-white/70">
          Bill-date dashboard · Concurrent-safe stock · Voidable payments &amp; fulfillment
        </footer>
      </section>

      {/* Form column */}
      <section className="flex min-w-0 flex-col justify-center px-4 py-8 sm:px-10 sm:py-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className={cn("mx-auto w-full min-w-0", wide ? "max-w-lg" : "max-w-md")}
        >
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary-600 text-white">
              <Wheat className="h-5 w-5" />
            </span>
            <span className="text-base font-semibold">{APP_NAME}</span>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
          <div className="mt-6 min-w-0">{children}</div>
          {footer && <div className="mt-6 text-sm text-ink-muted">{footer}</div>}
        </motion.div>
      </section>
    </div>
  );
}
