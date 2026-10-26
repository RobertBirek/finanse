import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ContextualSidebar } from "./ContextualSidebar";
import { getContextForPathname } from "./navigation";

describe("Unified sidebar", () => {
  it("keeps every real module reachable without the removed icon rail", () => {
    render(
      <MemoryRouter initialEntries={["/finances"]}>
        <ContextualSidebar
          context={getContextForPathname("/finances")}
          user={null}
          onLogout={vi.fn()}
        />
      </MemoryRouter>,
    );
    for (const [name, href] of [
      ["Dzisiaj", "/today"],
      ["Inbox", "/inbox"],
      ["Kalendarz", "/calendar"],
      ["Projekty", "/projects"],
      ["Finanse", "/finances"],
      ["Dokumenty", "/documents"],
      ["Ustawienia", "/settings"],
    ]) {
      expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(
      screen.queryByRole("link", { name: "Konta" }),
    ).not.toBeInTheDocument();
  });
});
