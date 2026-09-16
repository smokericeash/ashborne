import { Bell, ChevronDown, LogOut, Menu, Radio } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../../context/useAuth";
import { useLive } from "../../context/useLive";
import { cn, humanize, initials } from "../../lib/utils";
import { Button } from "../ui";

export function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { user, logout } = useAuth();
  const { connected } = useLive();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-20 flex h-[72px] items-center gap-3 border-b border-line/60 bg-void/80 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
      <button
        className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/5 lg:hidden"
        aria-label="Open navigation"
        onClick={onOpenMenu}
      >
        <Menu className="h-5 w-5" />
      </button>
      <div className="hidden items-center gap-2 rounded-lg border border-line/70 bg-panel/60 px-3 py-2 sm:flex">
        <Radio
          className={cn(
            "h-3.5 w-3.5",
            connected ? "text-kandor-400" : "text-slate-600",
          )}
        />
        <span className="text-[10px] font-semibold uppercase tracking-[.12em] text-slate-500">
          Live telemetry
        </span>
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            connected
              ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.8)]"
              : "bg-slate-600",
          )}
        />
      </div>
      <div className="ml-auto flex items-center gap-2">
        <Button
          className="relative w-9 px-0"
          variant="ghost"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
          <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-kandor-400" />
        </Button>
        <div className="relative">
          <button
            className="flex h-10 items-center gap-2 rounded-lg border border-transparent px-1.5 text-left hover:border-line hover:bg-panel"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
          >
            <span className="grid h-7 w-7 place-items-center rounded-md border border-kandor-400/20 bg-kandor-400/10 text-[10px] font-bold text-kandor-200">
              {initials(user?.display_name || user?.email)}
            </span>
            <span className="hidden max-w-36 sm:block">
              <span className="block truncate text-xs font-medium text-slate-200">
                {user?.display_name || user?.email}
              </span>
              <span className="block text-[9px] uppercase tracking-[.1em] text-slate-600">
                {user ? humanize(user.role) : ""}
              </span>
            </span>
            <ChevronDown className="hidden h-3.5 w-3.5 text-slate-600 sm:block" />
          </button>
          {menuOpen && (
            <div className="surface absolute right-0 mt-2 w-48 animate-slide-in rounded-lg p-1.5 shadow-2xl">
              <button
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-100"
                onClick={() => void logout()}
              >
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
