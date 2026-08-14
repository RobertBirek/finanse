import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useLogout } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { ContextualSidebar } from "./ContextualSidebar";
import { IconRail } from "./IconRail";
import { getContextForPathname } from "./navigation";

export function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activeContext = getContextForPathname(location.pathname);

  return (
    <div className="h-screen flex overflow-hidden bg-gray-950">
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div
        className={`fixed inset-y-0 left-0 z-50 w-60 transform transition-transform duration-200 lg:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <ContextualSidebar
          context={activeContext}
          user={user}
          onLogout={() => logout.mutate()}
          onNavigate={() => setMobileOpen(false)}
        />
      </div>

      <div className="hidden lg:flex h-full">
        <IconRail activeContext={activeContext} />
        <ContextualSidebar
          context={activeContext}
          user={user}
          onLogout={() => logout.mutate()}
        />
      </div>

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-14 flex items-center gap-4 px-4 border-b border-gray-800 bg-gray-950 lg:px-6">
          <button
            type="button"
            className="lg:hidden p-1 text-gray-400 hover:text-white"
            onClick={() => setMobileOpen(true)}
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <div className="flex-1" />
        </header>
        <div className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
