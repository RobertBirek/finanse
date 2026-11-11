import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ScheduleHistory } from "./ScheduleHistory";
import { importTestWrapper } from "../../../test/bankImportFixtures";
import { installScheduleServer } from "../../../test/loanScheduleFixtures";

let server: ReturnType<typeof installScheduleServer>;
afterEach(() => server?.restore());
it("reads bank originals and manual baseline snapshots separately from active sums", async () => {
  server = installScheduleServer();
  render(importTestWrapper(<ScheduleHistory loanId="loan-a" />).node);
  fireEvent.click(
    screen.getByRole("button", { name: "Historia wersji harmonogramu" }),
  );
  expect(
    await screen.findByRole("link", {
      name: "Pobierz oryginał wersji: schedule.pdf",
    }),
  ).toHaveAttribute("href", "/api/documents/document-a/original");
  fireEvent.change(screen.getByLabelText("Wersja harmonogramu"), {
    target: { value: "manual-version" },
  });
  expect(
    await screen.findByText("Baza ręczna — bez bankowego oryginału PDF."),
  ).toBeVisible();
  expect(screen.getByText(/nie są doliczane ponownie/i)).toBeVisible();
});
