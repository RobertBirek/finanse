import { Fragment } from "react";
import { Link, useLocation } from "react-router-dom";
import { PrimaryNavigation } from "./IconRail";
import {
  contextualMenuLabel,
  financeNavigationSearch,
  menuItemCurrent,
  type NavigationContext,
} from "./navigation";
import { LogoutIcon } from "./navigation-icons";

type SidebarUser = { display_name: string; email: string };
type ContextualSidebarProps = {
  context: NavigationContext;
  onNavigate?: () => void;
  showAllContexts?: boolean;
};

export function ContextualSidebar({
  context,
  onNavigate,
  showAllContexts = false,
}: ContextualSidebarProps) {
  const { pathname, search } = useLocation();
  const ContextIcon = context.icon;
  const finance = context.id === "finance";
  const menuLabel = contextualMenuLabel(context);
  const suffix = finance ? financeNavigationSearch(search) : "";
  return (
    <aside
      className={`context-sidebar ${showAllContexts ? "context-sidebar-mobile" : ""}`}
    >
      {!showAllContexts && (
        <div className="context-sidebar-title">
          <ContextIcon className="size-4" />
          {context.label}
        </div>
      )}
      <div className="context-sidebar-scroll">
        {menuLabel && (
          <nav className="space-y-1" aria-label={menuLabel}>
            {showAllContexts && (
              <p className="context-caption">{context.label}</p>
            )}
            {context.items.map((item, index) => (
              <Fragment key={item.to}>
                {item.group &&
                  item.group !== context.items[index - 1]?.group && (
                    <p className="context-caption">{item.group}</p>
                  )}
                <Link
                  to={item.to + suffix}
                  onClick={onNavigate}
                  aria-current={menuItemCurrent(item, pathname)}
                  className="context-link"
                >
                  <span className="context-marker" aria-hidden="true" />
                  {item.label}
                </Link>
              </Fragment>
            ))}
          </nav>
        )}
        {showAllContexts && (
          <>
            <p className="context-caption">Obszary aplikacji</p>
            <PrimaryNavigation onNavigate={onNavigate} />
          </>
        )}
      </div>
    </aside>
  );
}

export function NavigationProfile({
  user,
  onLogout,
}: {
  user: SidebarUser | null;
  onLogout: () => void;
}) {
  return (
    <div className="context-profile">
      <span className="profile-initial" aria-hidden="true">
        {user?.display_name.charAt(0).toUpperCase() || "?"}
      </span>
      <div className="navigation-profile-details min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">
          {user?.display_name || "Użytkownik"}
        </p>
        <p className="truncate text-xs text-[var(--ui-muted)]">{user?.email}</p>
      </div>
      <button
        type="button"
        className="context-logout"
        aria-label="Wyloguj"
        title="Wyloguj"
        onClick={onLogout}
      >
        <LogoutIcon className="size-4" />
      </button>
    </div>
  );
}
