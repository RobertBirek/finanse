import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { ContextualSidebar } from "../components/ContextualSidebar";
import { getContextForPathname } from "../components/navigation";

vi.mock("../stores/authStore", () => ({
  useAuthStore: (select: (state: { user: null }) => unknown) =>
    select({ user: null }),
}));
describe("Settings navigation", () => {
  it("opens OpenAI settings from global settings", () => {
    render(
      <MemoryRouter>
        <Settings />
        <ContextualSidebar context={getContextForPathname("/settings")} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Ustawienia AI" })).toHaveAttribute(
      "href",
      "/settings/ai",
    );
  });

  it("makes all financial definitions reachable from global settings", () => {
    render(
      <MemoryRouter>
        <Settings />
        <ContextualSidebar context={getContextForPathname("/settings")} />
      </MemoryRouter>,
    );
    for (const [name, path] of [
      ["Konta i rachunki", "accounts"],
      ["Kategorie", "categories"],
      ["Limity budżetu", "budgets"],
      ["Harmonogramy", "schedules"],
      ["Prognoza", "forecast"],
      ["Karty kredytowe", "cards"],
    ]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "href",
        `/settings/finances/${path}`,
      );
    }
  });
});
