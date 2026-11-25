import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Layout } from "../components/Layout";
import { FinanceSettings } from "./FinanceSettings";
import { Settings } from "./Settings";

vi.mock("../stores/authStore", () => ({
  useAuthStore: (select: (state: { user: null }) => unknown) =>
    select({ user: null }),
}));
vi.mock("../api/auth", () => ({ useLogout: () => ({ mutate: vi.fn() }) }));
vi.mock("../components/documents/DocumentProcessingMonitor", () => ({
  DocumentProcessingMonitor: () => null,
}));

function openSettings(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/settings" element={<Settings />} />
          <Route path="/settings/ai" element={<h1>Ustawienia AI</h1>} />
          <Route path="/settings/finances" element={<FinanceSettings />}>
            <Route path="cards/:id" element={<h1>Szczegóły karty</h1>} />
          </Route>
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Settings navigation", () => {
  it("links to AI from the sidebar instead of the general settings content", () => {
    openSettings("/settings");
    const nav = within(
      screen.getByRole("navigation", { name: "Widoki ustawień" }),
    );
    expect(nav.getByRole("link", { name: "Ustawienia AI" })).toHaveAttribute(
      "href",
      "/settings/ai",
    );
    expect(nav.getByRole("link", { name: "Ogólne" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const content = within(screen.getByRole("main"));
    expect(
      content.getByRole("heading", { name: "Profil" }),
    ).toBeInTheDocument();
    expect(
      content.queryByRole("link", { name: "Ustawienia AI" }),
    ).not.toBeInTheDocument();
  });

  it("keeps all finance destinations in the sidebar and identifies the parent of a card detail", () => {
    openSettings("/settings/finances/cards/card-a");
    const nav = within(
      screen.getByRole("navigation", { name: "Widoki ustawień" }),
    );
    for (const [name, path] of [
      ["Konta i rachunki", "accounts"],
      ["Kategorie", "categories"],
      ["Kategoryzacja", "categorization"],
      ["Limity budżetu", "budgets"],
      ["Harmonogramy", "schedules"],
      ["Prognoza", "forecast"],
      ["Kredyty i pożyczki", "loans"],
      ["Karty kredytowe", "cards"],
    ]) {
      expect(nav.getByRole("link", { name })).toHaveAttribute(
        "href",
        `/settings/finances/${path}`,
      );
    }
    expect(nav.getByRole("link", { name: "Karty kredytowe" })).toHaveAttribute(
      "aria-current",
      "location",
    );
    const breadcrumb = screen.getByRole("navigation", {
      name: "Ścieżka nawigacji",
    });
    expect(breadcrumb).toHaveTextContent(
      "Ustawienia / Konfiguracja finansów / Karty kredytowe",
    );
    expect(
      within(screen.getByRole("main")).queryByRole("navigation"),
    ).not.toBeInTheDocument();
  });

  it("shows the same settings links in the mobile drawer and closes it on navigation", () => {
    openSettings("/settings");
    fireEvent.click(
      screen.getByRole("button", { name: "Otwórz menu aplikacji" }),
    );
    const drawer = within(
      screen.getByRole("dialog", { name: "Menu aplikacji" }),
    );
    const nav = drawer.getByRole("navigation", { name: "Widoki ustawień" });
    expect(within(nav).getAllByRole("link")).toHaveLength(10);
    fireEvent.click(within(nav).getByRole("link", { name: "Ustawienia AI" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Ustawienia AI" }),
    ).toBeInTheDocument();
  });
});
