import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  return (
    <div className="min-h-screen">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="min-h-screen lg:pl-64">
        <Topbar onOpenMenu={() => setSidebarOpen(true)} />
        <div
          className="border-b border-ashborne-400/15 bg-ashborne-400/[.035] px-4 py-2 text-center text-[9px] font-semibold uppercase tracking-[.16em] text-ashborne-200/80 sm:px-6"
          role="note"
        >
          Authorized lab use only · Enrolled hosts must be explicitly in scope ·
          Operator actions are audited
        </div>
        <main className="mx-auto max-w-[1600px] p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
