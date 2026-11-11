import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ScheduleDiff } from "./ScheduleDiff";
import { ScheduleConfirmation } from "./ScheduleConfirmation";
import { schedulePreview } from "../../../test/loanScheduleFixtures";

it("shows a cutover and preserved unpaid history separately from retired future rows", () => {
  render(<ScheduleDiff diff={schedulePreview.diff} />);
  expect(screen.getByText(/2026-11-11/)).toBeVisible();
  expect(screen.getByText(/Zachowana historia/)).toBeVisible();
  expect(screen.getByText(/Wycofane przyszłe raty/)).toBeVisible();
  expect(screen.getByText(/Nie oznaczamy.*zapłacon/i)).toBeVisible();
});

it("requires explicit confirmation and never activates a linked conflict", () => {
  const activate = vi.fn();
  const preview = {
    ...schedulePreview,
    diff: {
      ...schedulePreview.diff,
      conflicts: [
        {
          code: "linked_future_missing_or_changed",
          row_key: "1",
          installment_ids: ["installment-a"],
        },
      ],
    },
  };
  render(
    <ScheduleConfirmation
      preview={preview}
      current
      pending={false}
      onActivate={activate}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Aktywuj harmonogram" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "Aktywuj harmonogram" }),
  ).toBeDisabled();
  expect(activate).not.toHaveBeenCalled();
});

it("an outdated preview cannot be activated even after checking confirmation", () => {
  render(
    <ScheduleConfirmation
      preview={schedulePreview}
      current={false}
      pending={false}
      onActivate={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "Aktywuj harmonogram" }),
  ).toBeDisabled();
  expect(screen.getByText(/nieaktualny/i)).toBeVisible();
});
