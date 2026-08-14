import { render, screen } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ContextualSidebar } from "./ContextualSidebar";
import { IconRail } from "./IconRail";
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
});

describe("contextual navigation components", () => {
  it("renders accessible rail tooltips and keeps future menu entries disabled", () => {
    const finance = getContextForPathname("/finances");

    render(
      <MemoryRouter>
        <IconRail activeContext={finance} />
        <ContextualSidebar
          context={finance}
          user={{ display_name: "Anna", email: "anna@example.com" }}
          onLogout={() => undefined}
        />
      </MemoryRouter>,
    );

    const financeRailLink = screen
      .getAllByRole("link", { name: "Finanse" })
      .find((link) => link.hasAttribute("title"));

    expect(financeRailLink).toHaveAttribute("title", "Finanse");
    expect(screen.getByText("Budżet").parentElement).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(
      screen.queryByRole("link", { name: "Budżet" }),
    ).not.toBeInTheDocument();
  });
});

describe("Layout", () => {
  it("composes the finance rail and contextual menu from the current URL", () => {
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
      screen.getByRole("navigation", { name: "Obszary aplikacji" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("navigation", { name: "Finanse" })).toHaveLength(
      2,
    );
  });
});
