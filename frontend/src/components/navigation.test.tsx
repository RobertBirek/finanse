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
      <MemoryRouter>
        <ContextualSidebar
          context={finance}
          user={{ display_name: "Anna", email: "anna@example.com" }}
          onLogout={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Finanse" })).toHaveAttribute(
      "href",
      "/finances",
    );
    expect(screen.getByRole("link", { name: "Ustawienia" })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(screen.getByRole("link", { name: "Projekty" })).toHaveAttribute(
      "href",
      "/projects",
    );
  });
});

describe("Layout", () => {
  it("uses one contextual sidebar and a fixed mobile bottom navigation", () => {
    render(
      <MemoryRouter initialEntries={["/finances"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/finances" element={<Outlet />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.queryByRole("navigation", { name: "Obszary aplikacji" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Wszystkie obszary aplikacji" }),
    ).toBeInTheDocument();
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
