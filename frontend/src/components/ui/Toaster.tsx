import { Toaster as Sonner } from "sonner";

export { toast } from "sonner";

export default function Toaster() {
  return (
    <Sonner
      position="top-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast: "rounded-xl border border-line bg-surface text-ink shadow-lg",
          title: "text-sm font-semibold",
          description: "text-xs text-ink-muted",
        },
      }}
    />
  );
}
