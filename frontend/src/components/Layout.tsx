import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useLogout } from "../api/auth";
import { useAuthStore } from "../stores/authStore";
import { ContextualSidebar, NavigationProfile } from "./ContextualSidebar";
import { Dialog } from "./Dialog";
import { IconButton } from "./IconButton";
import { IconRail } from "./IconRail";
import { DocumentProcessingMonitor } from "./documents/DocumentProcessingMonitor";
import { FinanceActivityMonitor } from "./finance/FinanceActivityMonitor";
import {
  contextualMenuLabel,
  financeNavigationSearch,
  getContextForPathname,
  isMenuItemActive,
  navigationContexts,
} from "./navigation";
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
  const activeView = activeContext.items.find((item) =>
    isMenuItemActive(item, location.pathname),
  );
  const finance = activeContext.id === "finance";
  const hasContextualMenu = !!contextualMenuLabel(activeContext);
  const sectionHref =
    activeContext.to +
    (finance ? financeNavigationSearch(location.search) : "");
  const showSection = activeView && activeView.label !== activeContext.label;
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
    <div className="app-shell app-navigation-shell h-dvh flex overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:bg-[var(--ui-surface)] focus:p-3 focus:text-[var(--ui-ink)] focus:ring-2 focus:ring-[var(--ui-blue)]"
      >
        Przejdź do treści
      </a>
      {mobileOpen && (
        <Dialog
          label="Menu aplikacji"
          onClose={() => setMobileOpen(false)}
          drawer
          panelClassName="navigation-drawer w-72 max-w-[calc(100vw-2rem)] h-full flex flex-col"
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
            onNavigate={() => setMobileOpen(false)}
            showAllContexts
          />
        </Dialog>
      )}
      <div className="hidden lg:flex h-full">
        <IconRail />
        {hasContextualMenu && <ContextualSidebar context={activeContext} />}
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="app-navigation-header">
          <button
            type="button"
            aria-label="Otwórz menu aplikacji"
            aria-expanded={mobileOpen}
            aria-haspopup="dialog"
            className="navigation-menu-button lg:hidden"
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
          <nav aria-label="Ścieżka nawigacji" className="navigation-crumbs">
            {showSection && (
              <>
                {activeView.to === activeContext.to ? (
                  <span>{activeContext.label}</span>
                ) : (
                  <Link to={sectionHref}>{activeContext.label}</Link>
                )}
                <span aria-hidden="true">{" / "}</span>
                {activeView.group && (
                  <>
                    <span>{activeView.group}</span>
                    <span aria-hidden="true">{" / "}</span>
                  </>
                )}
              </>
            )}
            <strong aria-current="page">
              {activeView?.label ?? activeContext.label}
            </strong>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <IconButton
              icon="theme"
              onClick={() =>
                setTheme((current) => (current === "light" ? "dark" : "light"))
              }
              label={
                theme === "light" ? "Włącz ciemny motyw" : "Włącz jasny motyw"
              }
            />
            <div className="navigation-header-profile">
              <NavigationProfile user={user} onLogout={() => logout.mutate()} />
            </div>
          </div>
        </header>
        {activeContext.id === "today" && (
          <nav
            className="mobile-section-nav lg:hidden"
            aria-label="Widoki sekcji Dzisiaj"
          >
            {activeContext.items.map(
              ({ label, to }) =>
                to && (
                  <NavLink key={to} to={to} end>
                    {label}
                  </NavLink>
                ),
            )}
          </nav>
        )}
        <DocumentProcessingMonitor />
        {finance && <FinanceActivityMonitor />}
        <main
          id="main-content"
          tabIndex={0}
          className="flex-1 min-h-0 overflow-y-auto p-4 pb-24 lg:p-8"
        >
          <Suspense fallback={<p role="status">Ładowanie widoku…</p>}>
            <Outlet />
          </Suspense>
        </main>
        <nav
          className="mobile-bottom-nav lg:hidden"
          aria-label="Nawigacja mobilna"
        >
          {navigationContexts
            .filter((context) =>
              [
                "today",
                "finance",
                "organization",
                "advisor",
                "knowledge",
                "system",
              ].includes(context.id),
            )
            .map((context) => {
              const Icon = context.icon;
              const active = activeContext.id === context.id;
              return (
                <Link
                  key={context.id}
                  to={
                    finance && context.id === "finance"
                      ? sectionHref
                      : context.to
                  }
                  className={`mobile-bottom-link ${active ? "active" : ""}`}
                  aria-current={
                    active
                      ? location.pathname === context.to
                        ? "page"
                        : "location"
                      : undefined
                  }
                >
                  <Icon className="h-5 w-5" />
                  <span>{context.label}</span>
                </Link>
              );
            })}
        </nav>
      </div>
    </div>
  );
}
