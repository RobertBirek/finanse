import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";

test("decision support keeps facts and source links when OpenAI is unavailable", async ({
  page,
}) => {
  const api = await fixtures(page);
  const requests: string[] = [];
  await page.route("**/api/advisor/decisions/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const action = url.pathname.split("/decisions/")[1];
    requests.push(`${request.method()} ${action}`);
    switch (action) {
      case "attention":
        await route.fulfill({
          json: {
            as_of: "2026-11-21",
            items: [
              {
                kind: "payment",
                source_id: "synthetic",
                title: "Testowy czynsz",
                reason: "Termin płatności przypada dziś.",
                due_date: "2026-11-21",
                href: "/finances/cashflow",
              },
            ],
          },
        });
        break;
      case "attention/explain":
        await route.fulfill({
          status: 503,
          json: { detail: "Synthetic OpenAI failure" },
        });
        break;
      case "cashflow-scenario":
        expect(request.postDataJSON()).toEqual({
          expense_date: "2026-11-22",
          amount_pln_minor: 15000,
        });
        await route.fulfill({
          json: {
            baseline_minimum: {
              date: "2026-11-22",
              projected_balance_pln: 12000,
            },
            scenario_minimum: {
              date: "2026-11-22",
              projected_balance_pln: -3000,
            },
            first_negative_date: "2026-11-22",
            opening_balance_negative: false,
            next_payday: "2026-12-10",
            forecast_start: "2026-11-21",
            forecast_end: "2026-12-04",
            excluded_obligation_reasons: ["recurring_amount_unknown"],
            covers_day_before_payday: false,
          },
        });
        break;
      case "spending-comparison":
        expect(url.searchParams.get("days")).toBe("14");
        await route.fulfill({
          json: {
            previous_start: "2026-10-24",
            current_start: "2026-11-07",
            end_exclusive: "2026-11-21",
            previous_total_pln: 10000,
            current_total_pln: 16000,
            delta_pln: 6000,
            categories: [],
            transactions: [],
            truncated: false,
          },
        });
        break;
      default:
        await route.fallback();
    }
  });
  await page.goto("/advisor");
  const attention = page.getByRole("button", {
    name: "Co wymaga mojej uwagi?",
  });
  await expect(attention).toBeVisible();
  expect(requests).toEqual([]);
  await attention.press("Enter");
  await expect(
    page.getByRole("link", { name: "Otwórz prognozę płatności" }),
  ).toHaveAttribute("href", "/finances/cashflow");
  await page
    .getByRole("button", { name: "Objaśnij priorytety z OpenAI" })
    .press("Enter");
  await expect(page.getByRole("alert")).toHaveText(
    "Objaśnienie jest niedostępne.",
  );
  await expect(page.getByText("Testowy czynsz")).toBeVisible();

  await page.getByText("Symulator „co jeśli?”", { exact: true }).press("Enter");
  await page.getByLabel("Data wydatku").fill("2026-11-22");
  await page.getByLabel("Kwota wydatku (PLN)").fill("150,00");
  await page.getByRole("button", { name: "Oblicz wariant" }).click();
  await expect(
    page.getByText(/Prognoza pomija niektóre zobowiązania/),
  ).toBeVisible();
  await expect(
    page.getByText(/Pierwsze ujemne saldo na koniec dnia: 2026-11-22/),
  ).toBeVisible();

  await page
    .getByText("Co zmieniło moje wydatki?", { exact: true })
    .press("Enter");
  await page.getByLabel("Długość porównania").selectOption("14");
  await page.getByRole("button", { name: "Porównaj wydatki" }).click();
  await expect(page.getByText(/Różnica netto:.*60,00/)).toBeVisible();
  expect(requests).toEqual([
    "GET attention",
    "POST attention/explain",
    "POST cashflow-scenario",
    "GET spending-comparison",
  ]);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("benchmark sends two drafts without saving settings or requiring a key field", async ({
  page,
}) => {
  const api = await fixtures(page);
  const requests: unknown[] = [];
  await page.route("**/api/advisor/settings/benchmark", async (route) => {
    const request = route.request();
    expect(request.method()).toBe("POST");
    requests.push(request.postDataJSON());
    await route.fulfill({
      json: {
        suite_version: "advisor-v1",
        variants: [
          {
            model: "test-model",
            status: "failed",
            cases: [
              {
                case_id: "classify_task",
                status: "timeout",
                matches_expected: null,
                duration_ms: 15000,
                input_tokens: null,
                output_tokens: null,
              },
            ],
          },
          {
            model: "second-model",
            status: "ok",
            cases: [
              {
                case_id: "classify_task",
                status: "ok",
                matches_expected: true,
                duration_ms: 100,
                input_tokens: 34,
                output_tokens: 18,
              },
            ],
          },
        ],
      },
    });
  });
  await page.goto("/settings/ai");
  const section = page.getByRole("region", {
    name: "Porównanie modeli i instrukcji",
  });
  await expect(section.getByLabel("Model A")).toHaveValue("test-model");
  expect(requests).toEqual([]);
  await section.getByLabel("Model B").fill("second-model");
  await section.getByLabel("Instrukcje B (opcjonalne)").fill("Zwięźle.");
  await section
    .getByRole("button", { name: "Uruchom porównanie OpenAI" })
    .press("Enter");
  await expect(
    section.getByText(/Przekroczono czas oczekiwania/),
  ).toBeVisible();
  await expect(section.getByText(/Zgodna z oczekiwaniem/)).toBeVisible();
  await expect(section.getByText(/Tokeny wejścia: —/)).toBeVisible();
  expect(requests).toEqual([
    {
      variants: [
        { model: "test-model", instructions: null },
        { model: "second-model", instructions: "Zwięźle." },
      ],
    },
  ]);
  expect(api.mutations).toEqual([]);
  api.assertClean();
});
