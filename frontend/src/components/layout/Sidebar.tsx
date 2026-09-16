import {
  ClipboardList,
  FileSearch,
  Gauge,
  Settings,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../context/useAuth";
import { cn } from "../../lib/utils";
import { LogoMark } from "../ui";

const navigation = [
  { label: "Dashboard", to: "/dashboard", icon: Gauge },
  { label: "Agents", to: "/agents", icon: ShieldCheck },
  { label: "Tasks", to: "/tasks", icon: ClipboardList },
  { label: "Audit", to: "/audit", icon: FileSearch },
  { label: "Users", to: "/users", icon: Users, administratorOnly: true },
  {
    label: "Settings",
    to: "/settings",
    icon: Settings,
    administratorOnly: true,
  },
];

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const asideRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const [desktop, setDesktop] = useState(false);
  const hiddenOnMobile = !desktop && !open;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const navigation = asideRef.current;
    if (!navigation) return;
    if (hiddenOnMobile) navigation.setAttribute("inert", "");
    else navigation.removeAttribute("inert");
  }, [hiddenOnMobile]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!open || desktop) return;

    const navigation = asideRef.current;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !navigation) return;
      const focusable = Array.from(
        navigation.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (!focusable.length) return;
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
  }, [desktop, open]);

  return (
    <>
      {open && (
        <button
          className="fixed inset-0 z-30 bg-black/70 backdrop-blur-sm lg:hidden"
          aria-label="Close navigation"
          onClick={onClose}
        />
      )}
      <aside
        ref={asideRef}
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line/70 bg-obsidian/95 transition-transform duration-200 lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-hidden={hiddenOnMobile || undefined}
        aria-label={!desktop ? "Mobile navigation" : undefined}
        aria-modal={!desktop && open ? "true" : undefined}
        role={!desktop ? "dialog" : undefined}
      >
        <div className="flex h-[72px] items-center gap-3 border-b border-line/60 px-5">
          <LogoMark />
          <div className="min-w-0">
            <p className="text-[17px] font-bold tracking-[.22em] text-white">
              KANDOR
            </p>
            <p className="truncate text-[9px] uppercase tracking-[.12em] text-kandor-400/75">
              Agent Orchestration
            </p>
          </div>
          <button
            ref={closeButtonRef}
            className="ml-auto text-slate-500 lg:hidden"
            aria-label="Close menu"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-4 pb-2 pt-5">
          <p className="px-3 text-[9px] font-bold uppercase tracking-[.2em] text-slate-700">
            Command surface
          </p>
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Primary navigation">
          {navigation
            .filter(
              (item) =>
                !item.administratorOnly || user?.role === "ADMINISTRATOR",
            )
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    "group relative flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-slate-500 transition hover:bg-white/[.035] hover:text-slate-200",
                    isActive && "bg-kandor-400/[.07] text-kandor-200",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute -left-3 h-5 w-0.5 rounded-r bg-kandor-400 shadow-signal" />
                    )}
                    <item.icon
                      className={cn(
                        "h-[17px] w-[17px]",
                        isActive
                          ? "text-kandor-400"
                          : "text-slate-600 group-hover:text-slate-400",
                      )}
                    />
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
        </nav>

        <div className="m-3 rounded-xl border border-line/70 bg-void/40 p-3.5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-30" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-[.12em] text-slate-400">
              Core operational
            </span>
          </div>
          <p className="mt-2 text-[10px] leading-4 text-slate-600">
            Allowlisted diagnostics only. All operator actions are audited.
          </p>
        </div>
      </aside>
    </>
  );
}
