import type { ComponentType } from "react";
import {
  CogIcon,
  DocumentIcon,
  FolderIcon,
  SparklesIcon,
  SunIcon,
  WalletIcon,
} from "./navigation-icons";

type IconComponent = ComponentType<{ className?: string }>;

export type NavigationMenuItem = {
  label: string;
  to?: string;
  soon?: boolean;
};

export type NavigationContext = {
  id:
    | "today"
    | "organization"
    | "finance"
    | "advisor"
    | "knowledge"
    | "automation"
    | "system";
  label: string;
  to?: string;
  icon: IconComponent;
  routePrefixes: string[];
  items: NavigationMenuItem[];
};

export const navigationContexts: NavigationContext[] = [
  {
    id: "today",
    label: "Dzisiaj",
    to: "/today",
    icon: SunIcon,
    routePrefixes: ["/today", "/inbox", "/calendar"],
    items: [
      { label: "Dzisiaj", to: "/today" },
      { label: "Inbox", to: "/inbox" },
      { label: "Kalendarz", to: "/calendar" },
    ],
  },
  {
    id: "organization",
    label: "Organizacja",
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
    items: [
      { label: "Finanse", to: "/finances" },
      { label: "Transakcje", to: "/finances/transactions" },
      { label: "Płynność", to: "/finances/cashflow" },
      { label: "Budżet", to: "/finances/budgets" },
      { label: "Raporty", to: "/finances/reports" },
    ],
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
    label: "Wiedza",
    to: "/documents",
    icon: DocumentIcon,
    routePrefixes: ["/documents"],
    items: [{ label: "Dokumenty", to: "/documents" }],
  },
  {
    id: "automation",
    label: "Automatyzacja",
    icon: CogIcon,
    routePrefixes: [],
    items: [
      { label: "Automatyzacje", soon: true },
      { label: "Reguły", soon: true },
    ],
  },
  {
    id: "system",
    label: "Ustawienia",
    to: "/settings",
    icon: CogIcon,
    routePrefixes: ["/settings"],
    items: [{ label: "Ustawienia", to: "/settings" }],
  },
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
  return (
    Boolean(item.to) &&
    (pathname === item.to || pathname.startsWith(`${item.to}/`))
  );
}
