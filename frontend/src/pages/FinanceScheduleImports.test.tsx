import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import { FinanceImports } from "./FinanceImports";
import { FinanceImportReview } from "./FinanceImportReview";
import { httpFailure, importTestWrapper } from "../test/bankImportFixtures";
import { installScheduleServer } from "../test/loanScheduleFixtures";

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
async function prepare() {
  await screen.findByLabelText("Kredyt");
  fireEvent.click(screen.getByLabelText(/Sprawdziłem przypisanie/));
  fireEvent.click(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  );
  await screen.findByRole("button", { name: "Aktywuj harmonogram" });
}

it("uploads a schedule as a plan, never as an executed payment", async () => {
  server = installScheduleServer();
  render(
    importTestWrapper(
      <FinanceImports />,
      "/finances/imports?kind=loan_schedule&loan=loan-a",
    ).node,
  );
  expect(
    await screen.findByText("Harmonogram nie księguje spłat"),
  ).toBeVisible();
  fireEvent.change(screen.getByLabelText("Pliki harmonogramów"), {
    target: {
      files: [new File(["synthetic"], "plan.pdf", { type: "application/pdf" })],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj pliki" }));
  await screen.findByRole("link", { name: "Sprawdź import" });
  expect(
    server.requests.find(
      (r) => r.url === "/finance/imports" && r.method === "post",
    )?.body,
  ).toEqual({ kind: "loan_schedule" });
  expect(
    server.requests.some(
      (r) =>
        r.url.endsWith("/activate-schedule") ||
        (r.url === "/finance/loans" && r.method === "post"),
    ),
  ).toBe(false);
});

it("preselects the URL loan without creating a contract and displays the source bank number", async () => {
  server = installScheduleServer();
  review();
  expect(await screen.findByLabelText("Kredyt")).toHaveValue("loan-a");
  expect(await screen.findByText(/Numer bankowy w wersji/)).toBeVisible();
  expect(
    server.requests.some(
      (r) => r.url === "/finance/loans" && r.method === "post",
    ),
  ).toBe(false);
});

it("new contract preview requires a name and two explicit distinct active PLN accounts", async () => {
  server = installScheduleServer();
  review();
  await screen.findByLabelText("Kredyt");
  fireEvent.click(screen.getByLabelText("Nowy kredyt"));
  expect(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Nazwa nowej umowy"), {
    target: { value: "Nowa umowa" },
  });
  expect(
    screen.queryByRole("option", { name: "Nieaktywne" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Karta" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Konto długu"), {
    target: { value: "debt-a" },
  });
  fireEvent.change(screen.getByLabelText("Konto spłaty"), {
    target: { value: "payer-a" },
  });
  fireEvent.click(screen.getByLabelText(/Sprawdziłem przypisanie/));
  expect(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).toBeEnabled();
});

it("activates only the frozen preview and shows a receipt without changing ledger balances", async () => {
  server = installScheduleServer();
  review();
  await prepare();
  expect(
    server.requests.some((r) => r.url.endsWith("/activate-schedule")),
  ).toBe(false);
  fireEvent.click(screen.getByLabelText(/Potwierdzam aktualizację planu/));
  fireEvent.click(screen.getByRole("button", { name: "Aktywuj harmonogram" }));
  expect(await screen.findByText("Harmonogram aktywowany")).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Otwórz kredyt i historię wersji" }),
  ).toHaveAttribute("href", "/settings/finances/loans?loan=loan-a");
  expect(screen.getByText(/Księga pozostaje bez zmian/)).toBeVisible();
  const request = server.requests.find((r) =>
    r.url.endsWith("/activate-schedule"),
  );
  expect(Object.keys(request!.body as object).sort()).toEqual([
    "preview_id",
    "request_hash",
  ]);
});

it("invalidates activation after 409 instead of replaying a stale preview", async () => {
  server = installScheduleServer({
    onRequest: (r) => {
      if (r.url.endsWith("/activate-schedule"))
        throw httpFailure(
          409,
          { code: "preview_stale", detail: "Przygotuj nowy podgląd" },
          r.config,
        );
    },
  });
  review();
  await prepare();
  fireEvent.click(screen.getByLabelText(/Potwierdzam aktualizację planu/));
  fireEvent.click(screen.getByRole("button", { name: "Aktywuj harmonogram" }));
  await screen.findByText("Przygotuj nowy podgląd");
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Aktywuj harmonogram" }),
    ).not.toBeInTheDocument(),
  );
});

it("shows a linked conflict but never permits activation", async () => {
  server = installScheduleServer({ conflict: true });
  review();
  await prepare();
  expect(
    screen.getByRole("button", { name: "Aktywuj harmonogram" }),
  ).toBeDisabled();
  expect(
    server.requests.some((r) => r.url.endsWith("/activate-schedule")),
  ).toBe(false);
});

it("keeps preview disabled when an existing target account is inactive", async () => {
  server = installScheduleServer({
    onRequest: (r) =>
      r.url === "/finance/accounts"
        ? [
            {
              id: "debt-a",
              name: "Nieaktywny dług",
              type: "credit",
              currency: "PLN",
              is_active: false,
            },
            {
              id: "payer-a",
              name: "Płatnik",
              type: "checking",
              currency: "PLN",
              is_active: true,
            },
          ]
        : undefined,
  });
  review();
  await screen.findByLabelText("Kredyt");
  fireEvent.click(screen.getByLabelText(/Sprawdziłem przypisanie/));
  expect(
    screen.getByRole("button", { name: "Przygotuj podgląd harmonogramu" }),
  ).toBeDisabled();
});

it("recovers an uncertain activation without creating a new intent", async () => {
  let lookups = 0;
  server = installScheduleServer({
    onRequest: (r) => {
      if (r.url.endsWith("/activate-schedule"))
        throw httpFailure(503, {}, r.config);
      if (r.url.includes("/commands/") && ++lookups === 1)
        throw httpFailure(404, {}, r.config);
    },
  });
  review();
  await prepare();
  fireEvent.click(screen.getByLabelText(/Potwierdzam aktualizację planu/));
  fireEvent.click(screen.getByRole("button", { name: "Aktywuj harmonogram" }));
  expect(await screen.findByText("Harmonogram aktywowany")).toBeVisible();
  expect(
    server.requests.filter((r) => r.url.endsWith("/activate-schedule")),
  ).toHaveLength(1);
  expect(lookups).toBeGreaterThanOrEqual(2);
});
