import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

vi.mock("../stores/authStore", () => ({
  useAuthStore: (select: (state: { user: null }) => unknown) =>
    select({ user: null }),
}));
describe("Settings navigation", () => {
  it("makes all financial definitions reachable from global settings", () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    for (const [name, path] of [
      ["Konta i rachunki", "accounts"],
      ["Kategorie", "categories"],
      ["Limity budżetu", "budgets"],
      ["Harmonogramy", "schedules"],
      ["Prognoza", "forecast"],
    ]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "href",
        `/settings/finances/${path}`,
      );
    }
  });
});
