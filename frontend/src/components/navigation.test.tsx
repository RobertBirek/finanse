import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ContextualSidebar } from "./ContextualSidebar";
import { Layout } from "./Layout";
import {
  getContextForPathname,
  isMenuItemActive,
  navigationContexts,
} from "./navigation";

vi.mock("../stores/authStore", () => ({
  useAuthStore: (
    selector: (state: {
      user: { display_name: string; email: string };
    }) => unknown,
  ) => selector({ user: { display_name: "Anna", email: "anna@example.com" } }),
}));

vi.mock("../api/auth", () => ({
  useLogout: () => ({ mutate: vi.fn() }),
}));

// These tests exercise navigation; processing feedback has its own real Layout integration tests.
vi.mock("./documents/DocumentProcessingMonitor", () => ({
  DocumentProcessingMonitor: () => null,
}));

describe("getContextForPathname", () => {
  it("uses the context with the longest matching route prefix", () => {
    expect(getContextForPathname("/projects/project-42").id).toBe(
      "organization",
    );
    expect(getContextForPathname("/finances/cashflow").id).toBe("finance");
  });

  it("falls back to today for a pathname outside the configuration", () => {
    expect(getContextForPathname("/unknown").id).toBe("today");
  });
});

describe("isMenuItemActive", () => {
  const projects = navigationContexts.find(
    (context) => context.id === "organization",
  )!.items[0];

  it("marks nested routes active without matching a sibling prefix", () => {
    expect(isMenuItemActive(projects, "/projects/project-42")).toBe(true);
    expect(isMenuItemActive(projects, "/projects-archive")).toBe(false);
  });

  it("marks the matching finance route active", () => {
    const reports = navigationContexts
      .find((context) => context.id === "finance")!
      .items.find((item) => item.label === "Raporty")!;

    expect(isMenuItemActive(reports, "/finances/reports")).toBe(true);
    expect(isMenuItemActive(reports, "/finances/budgets")).toBe(false);
  });

  it("keeps daily finance navigation separate from finance configuration", () => {
    const finance = navigationContexts.find(
      (context) => context.id === "finance",
    )!;
    const labels = finance.items.map((item) => item.label);

    expect(labels).not.toContain("Konta");
    expect(labels).toContain("Transakcje");
  });
});

describe("contextual navigation components", () => {
  it("renders the daily finance routes in the contextual sidebar", () => {
    const finance = getContextForPathname("/finances");

    render(
      <MemoryRouter
        initialEntries={[
          "/finances/imports/batch-42?month=2&year=2026&document=pdf",
        ]}
      >
        <ContextualSidebar context={finance} />
      </MemoryRouter>,
    );

    const submenu = screen.getByRole("navigation", { name: "Widoki finansów" });
    expect(within(submenu).getAllByRole("link")).toHaveLength(9);
    expect(
      within(submenu).getByRole("link", { name: "Import" }),
    ).toHaveAttribute("aria-current", "location");
    expect(
      within(submenu).getByRole("link", { name: "Przegląd" }),
    ).not.toHaveAttribute("aria-current");
    expect(
      within(submenu).getByRole("link", { name: "Raporty" }),
    ).toHaveAttribute("href", "/finances/reports?month=2&year=2026");
  });
});

describe("Layout", () => {
  it("does not duplicate primary destinations in a contextual panel outside Finance", () => {
    render(
      <MemoryRouter initialEntries={["/projects/project-42"]}>
        <Layout />
      </MemoryRouter>,
    );
    const rail = screen.getByRole("navigation", {
      name: "Wszystkie obszary aplikacji",
    });
    expect(
      within(rail).getByRole("link", { name: "Projekty" }),
    ).toHaveAttribute("aria-current", "location");
    expect(
      screen.queryByRole("navigation", { name: "Widoki sekcji Projekty" }),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("banner")).getByRole("button", {
        name: "Wyloguj",
      }),
    ).toBeInTheDocument();
  });

  it("uses the finance rail and submenu with a section breadcrumb", () => {
    render(
      <MemoryRouter
        initialEntries={["/finances/transactions?month=2&year=2026"]}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route path="/finances/transactions" element={<Outlet />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const rail = screen.getByRole("navigation", {
      name: "Wszystkie obszary aplikacji",
    });
    expect(within(rail).getByRole("link", { name: "Finanse" })).toHaveAttribute(
      "aria-current",
      "location",
    );
    const breadcrumb = screen.getByRole("navigation", {
      name: "Ścieżka nawigacji",
    });
    expect(
      within(breadcrumb).getByRole("link", { name: "Finanse" }),
    ).toHaveAttribute("href", "/finances?month=2&year=2026");
    expect(within(breadcrumb).getByText("Transakcje")).toHaveAttribute(
      "aria-current",
      "page",
    );
    const mobile = screen.getByRole("navigation", {
      name: "Nawigacja mobilna",
    });
    expect(within(mobile).getByRole("link", { name: "Finanse" })).toHaveClass(
      "active",
    );
    expect(
      within(mobile).getByRole("link", { name: "Ustawienia" }),
    ).toHaveAttribute("href", "/settings");
  });
});

describe("mobile navigation lifecycle", () => {
  it("shows finance views first in the drawer and closes when a view is chosen", () => {
    render(
      <MemoryRouter initialEntries={["/finances?month=2&year=2026"]}>
        <Layout />
      </MemoryRouter>,
    );
    const trigger = screen.getByRole("button", {
      name: "Otwórz menu aplikacji",
    });
    fireEvent.click(trigger);
    const drawer = within(
      screen.getByRole("dialog", { name: "Menu aplikacji" }),
    );
    const views = drawer.getByRole("navigation", { name: "Widoki finansów" });
    expect(drawer.getAllByRole("navigation")[0]).toBe(views);
    fireEvent.click(within(views).getByRole("link", { name: "Budżet" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      within(
        screen.getByRole("navigation", { name: "Ścieżka nawigacji" }),
      ).getByText("Budżet"),
    ).toBeInTheDocument();
  });
  it("only mounts the mobile menu when open and provides all application areas", () => {
    render(
      <MemoryRouter initialEntries={["/today"]}>
        <Layout />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", {
      name: "Otwórz menu aplikacji",
    });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Menu aplikacji" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    for (const label of [
      "Finanse",
      "Projekty",
      "Dokumenty",
      "Doradca",
      "Ustawienia",
      "Inbox",
      "Kalendarz",
    ])
      expect(
        within(dialog).getByRole("link", { name: label }),
      ).toBeInTheDocument();
    fireEvent(
      dialog,
      new Event("cancel", { bubbles: false, cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
  it("does not mark the finance overview active on a detail page", () => {
    const item = navigationContexts.find((c) => c.id === "finance")!.items[0];
    expect(isMenuItemActive(item, "/finances/accounts")).toBe(false);
    expect(isMenuItemActive(item, "/finances")).toBe(true);
  });
});
