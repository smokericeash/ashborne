import { createContext, useContext } from "react";

export type ToastTone = "success" | "error" | "info";

export const ToastContext = createContext<{
  notify: (message: string, tone?: ToastTone) => void;
} | null>(null);

export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used within ToastProvider");
  return value;
}
