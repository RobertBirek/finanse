import { useId, useRef, useState } from "react";
import { NavLink, useInRouterContext, useLocation } from "react-router-dom";
import { useAuthStore } from "../../stores/authStore";
import { RuleEventWatcher } from "./RuleEventWatcher";
import { SuggestionActivityWatcher } from "./SuggestionActivityWatcher";
import { financePeriodSearch, periodFromSearch } from "./useFinancePeriod";
import { primaryFinanceItems, secondaryFinanceItems } from "../navigation";

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
  const [expandedAt, setExpandedAt] = useState<string | null>(null);
  const expanded = expandedAt === location.key;
  const extraId = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const periodSearch = financePeriodSearch(
    periodFromSearch(new URLSearchParams(location.search)),
  );
  return (
    <nav
      className="finance-tabs"
      aria-label="Widoki finansów"
      onKeyDown={(event) => {
        if (event.key === "Escape" && expanded) {
          setExpandedAt(null);
          toggle.current?.focus();
        }
      }}
    >
      {primaryFinanceItems.map(({ to, label, end }) => (
        <NavLink key={to} to={`${to}${periodSearch}`} end={end}>
          {label}
        </NavLink>
      ))}
      <button
        type="button"
        className="finance-tabs-toggle"
        ref={toggle}
        aria-expanded={expanded}
        aria-controls={extraId}
        onClick={() => setExpandedAt(expanded ? null : location.key)}
      >
        Więcej
      </button>
      <div id={extraId} className="finance-tabs-more" data-expanded={expanded}>
        {secondaryFinanceItems.map(({ to, label }) => (
          <NavLink
            key={to}
            to={`${to}${periodSearch}`}
            onClick={() => setExpandedAt(null)}
          >
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

function FinanceTabLabels() {
  return (
    <nav className="finance-tabs" aria-label="Widoki finansów">
      {[...primaryFinanceItems, ...secondaryFinanceItems].map(({ label }) => (
        <span key={label}>{label}</span>
      ))}
    </nav>
  );
}
