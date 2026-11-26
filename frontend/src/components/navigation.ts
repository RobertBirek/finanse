import type { ComponentType } from "react";
import {
  CalendarIcon,
  CogIcon,
  DocumentIcon,
  FolderIcon,
  InboxIcon,
  SparklesIcon,
  SunIcon,
  WalletIcon,
} from "./navigation-icons";
import {
  financePeriodSearch,
  periodFromSearch,
} from "./finance/useFinancePeriod";

type IconComponent = ComponentType<{ className?: string }>;

export type NavigationMenuItem = {
  label: string;
  to: string;
  end?: boolean;
  icon?: IconComponent;
  group?: string;
};

export type NavigationContext = {
  id: "today" | "organization" | "finance" | "advisor" | "knowledge" | "system";
  label: string;
  to: string;
  icon: IconComponent;
  routePrefixes: string[];
  items: NavigationMenuItem[];
};

const financeItems = [
  { label: "Przegląd", to: "/finances", end: true },
  { label: "Transakcje", to: "/finances/transactions" },
  { label: "Budżet", to: "/finances/budgets" },
  { label: "Płynność", to: "/finances/cashflow" },
  { label: "Faktury i paragony", to: "/finances/documents" },
  { label: "Import", to: "/finances/imports" },
  { label: "Propozycje", to: "/finances/proposals" },
  { label: "Raporty", to: "/finances/reports" },
  { label: "Osoby", to: "/finances/people" },
] satisfies NavigationMenuItem[];

const financeSettingsItems = [
  ["accounts", "Konta i rachunki"],
  ["categories", "Kategorie"],
  ["categorization", "Kategoryzacja"],
  ["budgets", "Limity budżetu"],
  ["schedules", "Harmonogramy"],
  ["forecast", "Prognoza"],
  ["loans", "Kredyty i pożyczki"],
  ["cards", "Karty kredytowe"],
].map(([path, label]) => ({
  label,
  to: `/settings/finances/${path}`,
  group: "Konfiguracja finansów",
}));

export const navigationContexts: NavigationContext[] = [
  {
    id: "today",
    label: "Dzisiaj",
    to: "/today",
    icon: SunIcon,
    routePrefixes: ["/today", "/inbox", "/calendar"],
    items: [
      { label: "Dzisiaj", to: "/today", icon: SunIcon },
      { label: "Inbox", to: "/inbox", icon: InboxIcon },
      { label: "Kalendarz", to: "/calendar", icon: CalendarIcon },
    ],
  },
  {
    id: "organization",
    label: "Projekty",
    to: "/projects",
    icon: FolderIcon,
    routePrefixes: ["/projects"],
    items: [{ label: "Projekty", to: "/projects" }],
  },
  {
    id: "finance",
    label: "Finanse",
    to: "/finances",
    icon: WalletIcon,
    routePrefixes: ["/finances"],
    items: financeItems,
  },
  {
    id: "advisor",
    label: "Doradca",
    to: "/advisor",
    icon: SparklesIcon,
    routePrefixes: ["/advisor"],
    items: [{ label: "Doradca", to: "/advisor" }],
  },
  {
    id: "knowledge",
    label: "Dokumenty",
    to: "/documents",
    icon: DocumentIcon,
    routePrefixes: ["/documents"],
    items: [{ label: "Dokumenty", to: "/documents" }],
  },
  {
    id: "system",
    label: "Ustawienia",
    to: "/settings",
    icon: CogIcon,
    routePrefixes: ["/settings"],
    items: [
      { label: "Ogólne", to: "/settings", end: true },
      { label: "Ustawienia AI", to: "/settings/ai" },
      ...financeSettingsItems,
    ],
  },
];

export function contextualMenuLabel(context: NavigationContext) {
  if (context.id === "finance") return "Widoki finansów";
  if (context.id === "system") return "Widoki ustawień";
  return undefined;
}

const mainItems = navigationContexts.map(({ label, to, icon, id }) => ({
  label,
  to,
  icon,
  end: id === "today",
}));
const [, inbox, calendar] = navigationContexts[0].items;

export const primaryNavigationItems = [
  ...mainItems.slice(0, 1),
  inbox,
  mainItems[1],
  calendar,
  ...mainItems.slice(2),
];

export function getContextForPathname(pathname: string): NavigationContext {
  const match = navigationContexts
    .flatMap((context) =>
      context.routePrefixes
        .filter(
          (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
        )
        .map((prefix) => ({ context, prefix })),
    )
    .sort((left, right) => right.prefix.length - left.prefix.length)[0];

  return match?.context ?? navigationContexts[0];
}

export function isMenuItemActive(
  item: NavigationMenuItem,
  pathname: string,
): boolean {
  const path = pathname.replace(/\/+$/, "");
  return path === item.to || (!item.end && path.startsWith(`${item.to}/`));
}

export function menuItemCurrent(item: NavigationMenuItem, pathname: string) {
  if (!isMenuItemActive(item, pathname)) return undefined;
  return pathname.replace(/\/+$/, "") === item.to ? "page" : "location";
}

export function financeNavigationSearch(search: string) {
  return financePeriodSearch(periodFromSearch(new URLSearchParams(search)));
}
