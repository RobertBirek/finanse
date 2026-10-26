import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useLogout } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { ContextualSidebar } from "./ContextualSidebar";
import { Dialog } from "./Dialog";
import { getContextForPathname, navigationContexts } from "./navigation";
import {
  readThemePreference,
  writeThemePreference,
  type Theme,
} from "../lib/theme";

export function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useLogout();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(readThemePreference);
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
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    writeThemePreference(theme);
  }, [theme]);
  return (
    <div className="app-shell h-dvh flex overflow-hidden bg-gray-950">
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
          <p className="text-sm text-gray-300">
            Moja przestrzeń <span className="mx-2 text-gray-500">/</span>
            <strong>{activeContext.label}</strong>
          </p>
          <button
            type="button"
            className="ml-auto min-h-9 min-w-9 rounded-full border border-gray-700 text-sm text-gray-300 hover:bg-gray-800"
            onClick={() =>
              setTheme((current) => (current === "light" ? "dark" : "light"))
            }
            aria-label={
              theme === "light" ? "Włącz ciemny motyw" : "Włącz jasny motyw"
            }
          >
            {theme === "light" ? "◐" : "☀"}
          </button>
        </header>
        <div
          id="main-content"
          tabIndex={0}
          className="flex-1 min-h-0 overflow-y-auto p-4 pb-24 lg:p-8"
        >
          <Outlet />
        </div>
        <nav
          className="mobile-bottom-nav lg:hidden"
          aria-label="Nawigacja mobilna"
        >
          {navigationContexts
            .filter(
              (context) =>
                context.to &&
                [
                  "today",
                  "finance",
                  "organization",
                  "advisor",
                  "system",
                ].includes(context.id),
            )
            .map((context) => {
              const Icon = context.icon;
              const active =
                location.pathname === context.to ||
                location.pathname.startsWith(`${context.to}/`);
              return (
                <NavLink
                  key={context.id}
                  to={context.to!}
                  className={`mobile-bottom-link ${active ? "active" : ""}`}
                >
                  <Icon className="h-5 w-5" />
                  <span>
                    {context.id === "finance" ? "Finanse" : context.label}
                  </span>
                </NavLink>
              );
            })}
        </nav>
      </main>
    </div>
  );
}
