import { NavLink } from "react-router-dom";
import { type NavigationContext } from "./navigation";
import {
  CogIcon,
  DocumentIcon,
  FolderIcon,
  SparklesIcon,
  SunIcon,
  WalletIcon,
} from "./navigation-icons";

type SidebarUser = { display_name: string; email: string };
type ContextualSidebarProps = {
  context: NavigationContext;
  user: SidebarUser | null;
  onLogout: () => void;
  onNavigate?: () => void;
  showAllContexts?: boolean;
};
const items = [
  { label: "Dzisiaj", to: "/today", icon: SunIcon },
  { label: "Inbox", to: "/inbox", icon: FolderIcon },
  { label: "Projekty", to: "/projects", icon: FolderIcon },
  { label: "Kalendarz", to: "/calendar", icon: SunIcon },
  { label: "Finanse", to: "/finances", icon: WalletIcon },
  { label: "Doradca", to: "/advisor", icon: SparklesIcon },
  { label: "Dokumenty", to: "/documents", icon: DocumentIcon },
  { label: "Ustawienia", to: "/settings", icon: CogIcon },
];

export function ContextualSidebar({
  user,
  onLogout,
  onNavigate,
  showAllContexts = false,
}: ContextualSidebarProps) {
  return (
    <aside
      className={`unified-sidebar ${showAllContexts ? "w-full min-h-0 flex-1" : "w-56 shrink-0 h-full"}`}
    >
      <NavLink
        to="/today"
        className="advisor-brand"
        onClick={onNavigate}
        aria-label="Personal Advisor — strona główna"
      >
        <span className="advisor-monogram" aria-hidden="true">
          pa
        </span>
        <span>
          Personal
          <br />
          <strong>Advisor</strong>
        </span>
      </NavLink>
      <p className="sidebar-eyebrow">TWOJA PRZESTRZEŃ</p>
      <nav
        className="flex-1 space-y-1 overflow-y-auto"
        aria-label="Wszystkie obszary aplikacji"
      >
        {items.map(({ label, to, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? "active" : ""}`
            }
          >
            <Icon className="h-5 w-5 shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="mt-6 border-t border-gray-800 pt-4">
        <div className="flex min-w-0 items-center gap-3 px-3">
          <span className="profile-initial" aria-hidden="true">
            {user?.display_name.charAt(0).toUpperCase() || "?"}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {user?.display_name || "Użytkownik"}
            </p>
            <p className="truncate text-xs text-gray-500">{user?.email}</p>
          </div>
        </div>
        <button
          type="button"
          className="sidebar-link mt-2 w-full text-left"
          onClick={onLogout}
        >
          Wyloguj
        </button>
      </div>
    </aside>
  );
}
