import { NavLink, Outlet } from "react-router-dom";

const financeSettings = [
  ["accounts", "Konta i rachunki"],
  ["categories", "Kategorie"],
  ["budgets", "Limity budżetu"],
  ["schedules", "Harmonogramy"],
  ["forecast", "Prognoza"],
] as const;

export function FinanceSettings() {
  return (
    <div className="max-w-6xl">
      <header className="mb-6">
        <p className="text-xs font-semibold tracking-[0.14em] text-gray-500">
          USTAWIENIA · FINANSE
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-white">
          Konfiguracja finansów
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Konta, kategorie i plan definiujesz tutaj — codzienny widok pozostaje
          spokojny.
        </p>
      </header>
      <nav
        className="mb-6 flex gap-2 overflow-x-auto border-b border-gray-800 pb-3"
        aria-label="Ustawienia finansów"
      >
        {financeSettings.map(([path, label]) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `shrink-0 rounded-full px-3 py-2 text-sm ${isActive ? "bg-advisor-700 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"}`
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
