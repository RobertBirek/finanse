import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { FinanceImportReview } from "./FinanceImportReview";
import { importTestWrapper } from "../test/bankImportFixtures";
import {
  installScheduleServer,
  scheduleBatch,
  schedulePreview,
  scheduleReceipt,
} from "../test/loanScheduleFixtures";

let server: ReturnType<typeof installScheduleServer>;
afterEach(() => server?.restore());
function review() {
  render(
    importTestWrapper(
      <Routes>
        <Route
          path="/finances/imports/:batchId"
          element={<FinanceImportReview />}
        />
      </Routes>,
      "/finances/imports/batch-a?loan=loan-a",
    ).node,
  );
}

it("opens a committed source with its durable receipt after the in-memory intent is gone", async () => {
  const batch = scheduleBatch();
  server = installScheduleServer({
    onRequest: (r) =>
      r.url === "/finance/imports/batch-a"
        ? {
            ...batch,
            commit_state: "committed",
            unresolved_count: 0,
            sources: batch.sources.map((s) => ({
              ...s,
              schedule_activations: [
                { source_revision_id: "revision-a", result: scheduleReceipt },
              ],
            })),
          }
        : undefined,
  });
  review();
  expect(await screen.findByText("Harmonogram aktywowany")).toBeVisible();
  expect(screen.getByText(/schedule-receipt/)).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).not.toBeInTheDocument();
  expect(
    server.requests.some(
      (r) =>
        r.url.endsWith("/activate-schedule") ||
        r.url.endsWith("/schedule-preview"),
    ),
  ).toBe(false);
});

it("explicitly compares and selects a candidate, then points to the original receipt for identical results", async () => {
  const batch = scheduleBatch();
  server = installScheduleServer({
    onRequest: (r) => {
      if (r.url === "/finance/imports/batch-a")
        return {
          ...batch,
          sources: batch.sources.map((s) => ({
            ...s,
            candidate_revision_id: "revision-new",
            candidate_parser_version: "v2",
            schedule_activations: [
              { source_revision_id: "revision-a", result: scheduleReceipt },
            ],
          })),
        };
      if (r.url.endsWith("/schedule-preview"))
        return {
          ...schedulePreview,
          source_revision_id: "revision-new",
          existing_activation: scheduleReceipt,
        };
      return undefined;
    },
  });
  review();
  await screen.findByLabelText("Odczyt harmonogramu");
  fireEvent.change(screen.getByLabelText("Odczyt harmonogramu"), {
    target: { value: "revision-new" },
  });
  expect(await screen.findByText(/Porównanie odczytów źródła/)).toBeVisible();
  await screen.findByRole("combobox", { name: /^Kredyt$/ });
  fireEvent.click(screen.getByLabelText(/Sprawdziłem przypisanie/));
  expect(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/Porównałem odczyty/));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  );
  expect(
    await screen.findByText(/Odczyt zgodny z zapisaną wersją/),
  ).toBeVisible();
  const body = server.requests.find((r) => r.url.endsWith("/schedule-preview"))
    ?.body as { source_revision_id: string; acknowledgements: string[] };
  expect(body.source_revision_id).toBe("revision-new");
  expect(body.acknowledgements).toContain(
    "reparse_comparison:source-a:revision-new",
  );
  expect(
    screen.queryByRole("button", { name: "Aktywuj harmonogram" }),
  ).not.toBeInTheDocument();
  expect(
    server.requests.some((r) => r.url.endsWith("/activate-schedule")),
  ).toBe(false);
});

it("reopens an activation of the selected candidate without returning to an uncommitted original", async () => {
  const batch = scheduleBatch();
  server = installScheduleServer({
    onRequest: (r) =>
      r.url === "/finance/imports/batch-a"
        ? {
            ...batch,
            sources: batch.sources.map((s) => ({
              ...s,
              candidate_revision_id: "revision-new",
              candidate_parser_version: "v2",
              schedule_activations: [
                { source_revision_id: "revision-new", result: scheduleReceipt },
              ],
            })),
          }
        : undefined,
  });
  review();
  expect(await screen.findByText("Harmonogram aktywowany")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).not.toBeInTheDocument();
});

it("uses candidate controls rather than failed old checks after explicit revision choice", async () => {
  const batch = scheduleBatch();
  server = installScheduleServer({
    onRequest: (r) =>
      r.url === "/finance/imports/batch-a"
        ? {
            ...batch,
            sources: batch.sources.map((s) => ({
              ...s,
              candidate_revision_id: "revision-new",
              candidate_parser_version: "v2",
              checks: [
                {
                  code: "old_layout",
                  required: true,
                  result: "failed",
                  expected: 1,
                  actual: 0,
                },
              ],
              candidate_checks: [
                {
                  code: "new_layout",
                  required: true,
                  result: "passed",
                  expected: 1,
                  actual: 1,
                },
              ],
            })),
          }
        : undefined,
  });
  review();
  await screen.findByLabelText("Odczyt harmonogramu");
  fireEvent.change(screen.getByLabelText("Odczyt harmonogramu"), {
    target: { value: "revision-new" },
  });
  await screen.findByRole("combobox", { name: /^Kredyt$/ });
  fireEvent.click(screen.getByLabelText(/Sprawdziłem przypisanie/));
  await waitFor(() =>
    expect(screen.getByLabelText(/Porównałem odczyty/)).toBeEnabled(),
  );
  fireEvent.click(screen.getByLabelText(/Porównałem odczyty/));
  expect(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).toBeEnabled();
});
