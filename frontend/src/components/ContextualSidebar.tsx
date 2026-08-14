import { NavLink, useLocation } from "react-router-dom";
import { isMenuItemActive, type NavigationContext } from "./navigation";

type SidebarUser = {
  display_name: string;
  email: string;
};

type ContextualSidebarProps = {
  context: NavigationContext;
  user: SidebarUser | null;
  onLogout: () => void;
  onNavigate?: () => void;
};

export function ContextualSidebar({
  context,
  user,
  onLogout,
  onNavigate,
}: ContextualSidebarProps) {
  const { pathname } = useLocation();

  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-full">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-white flex items-center gap-2">
          <span className="w-8 h-8 rounded-lg bg-advisor-500 flex items-center justify-center text-sm font-bold">
            A
          </span>
          Advisor
        </h1>
      </div>

      <div className="px-4 py-3 border-b border-gray-800 text-xs font-semibold uppercase tracking-wide text-gray-500">
        {context.label}
      </div>

      <nav
        className="flex-1 p-3 space-y-1 overflow-y-auto"
        aria-label={context.label}
      >
        {context.items.map((item) =>
          item.to ? (
            <NavLink
              key={item.label}
              to={item.to}
              className={`sidebar-link ${
                isMenuItemActive(item, pathname) ? "active" : ""
              }`}
              onClick={onNavigate}
            >
              {item.label}
            </NavLink>
          ) : (
            <div
              key={item.label}
              className="sidebar-link cursor-not-allowed opacity-50"
              aria-disabled="true"
            >
              <span>{item.label}</span>
              <span className="ml-auto text-xs">Wkrótce</span>
            </div>
          ),
        )}
      </nav>

      <UserPanel user={user} onLogout={onLogout} />
    </aside>
  );
}

function UserPanel({
  user,
  onLogout,
}: {
  user: SidebarUser | null;
  onLogout: () => void;
}) {
  return (
    <div className="p-3 border-t border-gray-800">
      <div className="flex items-center gap-3 px-3 py-2">
        <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-sm font-medium">
          {user?.display_name.charAt(0).toUpperCase() || "?"}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-200 truncate">
            {user?.display_name || "Użytkownik"}
          </p>
          <p className="text-xs text-gray-500 truncate">{user?.email}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onLogout}
        className="w-full mt-2 px-3 py-2 text-sm text-gray-400 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors text-left"
      >
        Wyloguj
      </button>
    </div>
  );
}
