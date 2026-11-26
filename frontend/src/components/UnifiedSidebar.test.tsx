import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { IconRail } from "./IconRail";

describe("Primary icon rail", () => {
  it("keeps all eight modules reachable and highlights Inbox independently", () => {
    render(
      <MemoryRouter initialEntries={["/inbox"]}>
        <IconRail />
      </MemoryRouter>,
    );
    const nav = within(
      screen.getByRole("navigation", { name: "Wszystkie obszary aplikacji" }),
    );
    for (const [name, href] of [
      ["Dzisiaj", "/today"],
      ["Inbox", "/inbox"],
      ["Kalendarz", "/calendar"],
      ["Projekty", "/projects"],
      ["Finanse", "/finances"],
      ["Doradca", "/advisor"],
      ["Dokumenty", "/documents"],
      ["Ustawienia", "/settings"],
    ]) {
      expect(nav.getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(nav.getAllByRole("link")).toHaveLength(8);
    expect(nav.getByRole("link", { name: "Inbox" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(nav.getByRole("link", { name: "Dzisiaj" })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
