import { NavLink, useInRouterContext, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { RuleEventWatcher } from "./RuleEventWatcher";
import { SuggestionActivityWatcher } from "./SuggestionActivityWatcher";
import { financePeriodSearch, periodFromSearch } from "./useFinancePeriod";

const tabs = [
  ["/finances", "Przegląd", true],
  ["/finances/transactions", "Transakcje", false],
  ["/finances/budgets", "Budżet", false],
  ["/finances/cashflow", "Nadchodzące", false],
  ["/finances/documents", "Dokumenty", false],
  ["/finances/imports", "Import", false],
  ["/finances/proposals", "Propozycje", false],
  ["/finances/reports", "Raporty", false],
] as const;

export function FinanceTabs() {
  const inRouter = useInRouterContext();
  const authenticated = useAuthStore(
    (s) => s.authStatus === "authenticated" && !!s.user,
  );
  return (
    <>
      {authenticated ? <RuleEventWatcher /> : null}
      {authenticated ? <SuggestionActivityWatcher /> : null}
      {inRouter ? <FinanceTabLinks /> : <FinanceTabLabels />}
    </>
  );
}

function FinanceTabLinks() {
  const location = useLocation();
  const periodSearch = financePeriodSearch(
    periodFromSearch(new URLSearchParams(location.search)),
  );
  return (
    <nav
      className="mb-7 flex gap-6 overflow-x-auto border-b border-gray-800"
      aria-label="Widoki finansów"
    >
      {tabs.map(([to, label, end]) => (
        <NavLink
          key={to}
          to={`${to}${periodSearch}`}
          end={end}
          className={({ isActive }) =>
            `shrink-0 border-b-2 px-1 pb-3 text-sm ${isActive ? "border-current font-semibold text-gray-950 dark:text-white" : "border-transparent text-gray-500 hover:text-gray-950 dark:hover:text-white"}`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function FinanceTabLabels() {
  return (
    <nav
      className="mb-7 flex gap-6 overflow-x-auto border-b border-gray-800"
      aria-label="Widoki finansów"
    >
      {tabs.map(([, label]) => (
        <span
          key={label}
          className="shrink-0 border-b-2 border-transparent px-1 pb-3 text-sm text-gray-500"
        >
          {label}
        </span>
      ))}
    </nav>
  );
}
