import { useCallback, useMemo, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "../lib/utils";
import { ToastContext, type ToastTone } from "./useToast";

interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback(
    (id: number) =>
      setToasts((items) => items.filter((item) => item.id !== id)),
    [],
  );
  const notify = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = Date.now() + Math.random();
      setToasts((items) => [...items.slice(-3), { id, message, tone }]);
      window.setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((toast) => {
          const Icon =
            toast.tone === "success"
              ? CheckCircle2
              : toast.tone === "error"
                ? AlertCircle
                : Info;
          return (
            <div
              key={toast.id}
              className={cn(
                "surface pointer-events-auto flex animate-slide-in items-start gap-3 rounded-xl p-3.5 text-sm",
                toast.tone === "error" && "border-red-500/30",
              )}
            >
              <Icon
                className={cn(
                  "mt-0.5 h-4 w-4 shrink-0",
                  toast.tone === "success"
                    ? "text-emerald-400"
                    : toast.tone === "error"
                      ? "text-red-400"
                      : "text-cyan-400",
                )}
              />
              <span className="flex-1 text-slate-300">{toast.message}</span>
              <button
                aria-label="Dismiss notification"
                className="text-slate-600 hover:text-slate-300"
                onClick={() => dismiss(toast.id)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
