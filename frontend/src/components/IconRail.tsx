import { Link, useLocation } from "react-router-dom";
import {
  financeNavigationSearch,
  menuItemCurrent,
  primaryNavigationItems,
} from "./navigation";
import { Tooltip } from "./Tooltip";

export function PrimaryNavigation({
  compact = false,
  onNavigate,
}: {
  compact?: boolean;
  onNavigate?: () => void;
}) {
  const { pathname, search } = useLocation();
  const financeSearch =
    pathname === "/finances" || pathname.startsWith("/finances/")
      ? financeNavigationSearch(search)
      : "";
  return (
    <nav
      aria-label="Wszystkie obszary aplikacji"
      className={compact ? "icon-rail-nav" : "space-y-1"}
    >
      {primaryNavigationItems.map(({ label, icon: Icon, ...item }) => {
        const current = menuItemCurrent({ label, ...item }, pathname);
        const link = (
          <Link
            key={item.to}
            to={item.to === "/finances" ? item.to + financeSearch : item.to}
            onClick={onNavigate}
            aria-current={current}
            aria-label={compact ? label : undefined}
            className={compact ? "icon-rail-link" : "context-link"}
          >
            {Icon && <Icon className="size-5 shrink-0" />}
            {!compact && label}
          </Link>
        );
        return compact ? (
          <Tooltip key={item.to} label={label}>
            {link}
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

export function IconRail() {
  return (
    <div className="icon-rail">
      <span className="nav-monogram" aria-label="Personal Advisor" role="img">
        PA
      </span>
      <PrimaryNavigation compact />
    </div>
  );
}
