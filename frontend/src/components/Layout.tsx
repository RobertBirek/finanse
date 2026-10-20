import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useLogout } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { ContextualSidebar } from "./ContextualSidebar";
import { IconRail } from "./IconRail";
import { Dialog } from "./Dialog";
import { getContextForPathname } from "./navigation";

export function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const activeContext = getContextForPathname(location.pathname);
  useEffect(() => {
    setMobileOpen(false);
  }, [location.key]);
  useEffect(() => {
    const query = window.matchMedia?.("(min-width: 1024px)");
    const closeOnDesktop = () => {
      if (query?.matches) setMobileOpen(false);
    };
    query?.addEventListener("change", closeOnDesktop);
    return () => query?.removeEventListener("change", closeOnDesktop);
  }, []);
  return (
    <div className="h-dvh flex overflow-hidden bg-gray-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-gray-800 focus:p-3"
      >
        Przejdź do treści
      </a>
      {mobileOpen && (
        <Dialog
          label="Menu aplikacji"
          onClose={() => setMobileOpen(false)}
          drawer
          panelClassName="w-72 max-w-[calc(100vw-2rem)] h-full bg-gray-900 flex flex-col"
        >
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="btn-secondary m-3 shrink-0"
          >
            Zamknij menu
          </button>
          <ContextualSidebar
            context={activeContext}
            user={user}
            onLogout={() => logout.mutate()}
            onNavigate={() => setMobileOpen(false)}
            showAllContexts
          />
        </Dialog>
      )}
      <div className="hidden lg:flex h-full">
        <IconRail activeContext={activeContext} />
        <ContextualSidebar
          context={activeContext}
          user={user}
          onLogout={() => logout.mutate()}
        />
      </div>
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-14 shrink-0 flex items-center gap-4 px-4 border-b border-gray-800 bg-gray-950 lg:px-6">
          <button
            type="button"
            aria-label="Otwórz menu aplikacji"
            aria-expanded={mobileOpen}
            aria-haspopup="dialog"
            className="lg:hidden min-h-11 min-w-11 rounded-lg text-gray-300 hover:bg-gray-800"
            onClick={() => setMobileOpen(true)}
          >
            <svg
              aria-hidden="true"
              className="w-6 h-6 mx-auto"
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
          <p className="text-sm text-gray-300">{activeContext.label}</p>
        </header>
        <div
          id="main-content"
          tabIndex={0}
          className="flex-1 min-h-0 overflow-y-auto p-4 lg:p-6"
        >
          <Outlet />
        </div>
      </main>
    </div>
  );
}
