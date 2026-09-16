import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Inbox,
  LoaderCircle,
  RotateCw,
  X,
} from "lucide-react";
import {
  forwardRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from "react";
import type { AgentStatus, TaskStatus } from "../types";
import { cn, humanize } from "../lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "primary",
      size = "md",
      loading,
      children,
      disabled,
      ...props
    },
    ref,
  ) {
    const variants: Record<ButtonVariant, string> = {
      primary:
        "border-kandor-400/30 bg-kandor-400 text-slate-950 hover:bg-kandor-300 shadow-signal",
      secondary:
        "border-line bg-elevated text-slate-200 hover:border-slate-500 hover:bg-slate-800",
      ghost:
        "border-transparent bg-transparent text-slate-400 hover:bg-white/5 hover:text-slate-100",
      danger:
        "border-red-500/25 bg-red-500/10 text-red-300 hover:bg-red-500/20",
    };
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg border font-semibold transition active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
          size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
          variants[variant],
          className,
        )}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden />
        )}
        {children}
      </button>
    );
  },
);

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("field", className)} {...props} />;
});

export const Select = forwardRef<
  HTMLSelectElement,
  SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ className, ...props }, ref) {
  return (
    <select
      ref={ref}
      className={cn("field appearance-none pr-9", className)}
      {...props}
    />
  );
});

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("surface rounded-xl", className)} {...props} />;
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info" | "purple";
  className?: string;
}) {
  const tones = {
    neutral: "border-slate-600/40 bg-slate-700/20 text-slate-300",
    success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    warning: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    danger: "border-red-500/30 bg-red-500/10 text-red-300",
    info: "border-cyan-500/30 bg-cyan-500/10 text-cyan-300",
    purple: "border-violet-500/30 bg-violet-500/10 text-violet-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[.08em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: AgentStatus | TaskStatus }) {
  const tone =
    status === "ONLINE" || status === "SUCCESS"
      ? "success"
      : status === "DEGRADED" ||
          status === "QUEUED" ||
          status === "DISPATCHED" ||
          status === "EXPIRED"
        ? "warning"
        : status === "RUNNING"
          ? "info"
          : status === "CANCELLED"
            ? "neutral"
            : "danger";
  return (
    <Badge tone={tone}>
      <span
        className={cn(
          "mr-1.5 h-1.5 w-1.5 rounded-full bg-current",
          (status === "ONLINE" || status === "RUNNING") && "animate-pulse-soft",
        )}
      />
      {status}
    </Badge>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-end">
      <div>
        {eyebrow && (
          <p className="mb-1 text-[10px] font-bold uppercase tracking-[.22em] text-kandor-400">
            {eyebrow}
          </p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-white md:text-[28px]">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

export function SectionTitle({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/70 px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {description && (
          <p className="mt-0.5 text-xs text-slate-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function Spinner({ label = "Loading KANDOR" }: { label?: string }) {
  return (
    <div
      className="flex min-h-44 flex-col items-center justify-center gap-3 text-slate-500"
      role="status"
    >
      <div className="relative grid h-10 w-10 place-items-center rounded-xl border border-kandor-400/30 bg-kandor-400/5">
        <LoaderCircle className="h-5 w-5 animate-spin text-kandor-400" />
      </div>
      <span className="text-xs uppercase tracking-[.14em]">{label}</span>
    </div>
  );
}

export function PageLoader() {
  return (
    <div
      className="grid min-h-screen place-items-center bg-void"
      role="status"
      aria-label="Loading KANDOR"
    >
      <div className="text-center">
        <LogoMark className="mx-auto mb-4 h-14 w-14" />
        <p className="text-xs font-semibold uppercase tracking-[.24em] text-slate-500">
          Establishing secure session
        </p>
      </div>
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Unable to load data",
}: {
  error: Error | string;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div
      className="flex min-h-48 flex-col items-center justify-center p-8 text-center"
      role="alert"
    >
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl border border-red-500/20 bg-red-500/10">
        <AlertCircle className="h-5 w-5 text-red-400" />
      </div>
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      <p className="mt-1 max-w-md text-xs text-slate-500">
        {typeof error === "string" ? error : error.message}
      </p>
      {onRetry && (
        <Button
          className="mt-4"
          size="sm"
          variant="secondary"
          onClick={onRetry}
        >
          <RotateCw className="h-3.5 w-3.5" /> Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center p-8 text-center">
      <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl border border-line bg-white/[.02] text-slate-500">
        {icon ?? <Inbox className="h-5 w-5" />}
      </div>
      <h3 className="text-sm font-semibold text-slate-300">{title}</h3>
      <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
        {description}
      </p>
    </div>
  );
}

export function Pagination({
  skip,
  limit,
  total,
  onChange,
}: {
  skip: number;
  limit: number;
  total: number;
  onChange: (skip: number) => void;
}) {
  if (total <= 0) return null;
  const start = skip + 1;
  const end = Math.min(skip + limit, total);
  const page = Math.floor(skip / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="flex flex-col items-center justify-between gap-3 border-t border-line/70 px-4 py-3 text-xs text-slate-500 sm:flex-row">
      <span>
        Showing {start.toLocaleString()}–{end.toLocaleString()} of{" "}
        {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-2">
        <Button
          aria-label="Previous page"
          size="sm"
          variant="ghost"
          disabled={skip === 0}
          onClick={() => onChange(Math.max(0, skip - limit))}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-20 text-center">
          Page {page} / {pages}
        </span>
        <Button
          aria-label="Next page"
          size="sm"
          variant="ghost"
          disabled={skip + limit >= total}
          onClick={() => onChange(skip + limit)}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  width = "max-w-lg",
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const id = useId();
  const titleId = `modal-title-${id}`;
  const descriptionId = `modal-description-${id}`;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    const dialog = dialogRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const focusableSelector = [
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      '[tabindex]:not([tabindex="-1"])',
    ].join(",");

    document.body.style.overflow = "hidden";
    dialog?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;

      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(focusableSelector),
      ).filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      tabIndex={-1}
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <Card className={cn("w-full animate-slide-in overflow-hidden", width)}>
        <div className="flex items-start justify-between border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="font-semibold text-white">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-xs text-slate-500">
                {description}
              </p>
            )}
          </div>
          <Button
            aria-label="Close dialog"
            size="sm"
            variant="ghost"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {children}
      </Card>
    </div>
  );
}

export function LogoMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative grid h-9 w-9 place-items-center overflow-hidden rounded-[10px] border border-kandor-400/35 bg-kandor-400/[.07] shadow-signal",
        className,
      )}
      aria-hidden
    >
      <svg
        viewBox="0 0 32 32"
        className="h-[58%] w-[58%] fill-none stroke-kandor-300"
        strokeWidth="2.6"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        <path d="M7 5v22M8 16 22 5M8 16l15 11" />
        <path d="M20 5h5M21 27h5" className="opacity-40" />
      </svg>
      <span className="absolute right-1 top-1 h-1 w-1 rounded-full bg-kandor-300" />
    </div>
  );
}

export function KeyValue({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0 border-b border-line/50 py-3 last:border-0">
      <dt className="text-[10px] font-semibold uppercase tracking-[.12em] text-slate-600">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 truncate text-sm text-slate-200",
          mono && "font-mono text-xs",
        )}
      >
        {value || "—"}
      </dd>
    </div>
  );
}

export function FilterChip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <button
      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-kandor-400/20 bg-kandor-400/[.06] px-2 text-[11px] text-kandor-200"
      onClick={onRemove}
    >
      {humanize(label)} <X className="h-3 w-3" />
    </button>
  );
}
