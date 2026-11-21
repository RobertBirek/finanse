import { Link, NavLink, Outlet } from "react-router-dom";

const financeSettings = [
  ["accounts", "Konta i rachunki"],
  ["categories", "Kategorie"],
  ["categorization", "Kategoryzacja"],
  ["budgets", "Limity budżetu"],
  ["schedules", "Harmonogramy"],
  ["forecast", "Prognoza"],
  ["loans", "Kredyty i pożyczki"],
  ["cards", "Karty kredytowe"],
] as const;

export function FinanceSettings() {
  return (
    <div className="page-workspace">
      <nav className="page-heading-context" aria-label="Ścieżka nawigacji">
        <Link className="underline" to="/settings">
          Ustawienia
        </Link>
        <span aria-hidden="true"> / </span>
        <span>Konfiguracja finansów</span>
      </nav>
      <nav
        className="mb-6 flex gap-2 overflow-x-auto border-b border-gray-800 pb-3"
        aria-label="Ustawienia finansów"
      >
        {financeSettings.map(([path, label]) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `flex min-h-11 shrink-0 items-center rounded-full px-3 py-2 text-sm ${isActive ? "bg-advisor-700 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"}`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
