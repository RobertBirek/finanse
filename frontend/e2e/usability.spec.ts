import { expect, test } from "@playwright/test";
import { account, fixtures } from "./fixtures";

test("long account names wrap without colliding with actions", async ({
  page,
}) => {
  await fixtures(page);
  const longName = "Konto na wydatki rodzinne i oszczędności długoterminowe";
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({ json: [{ ...account, name: longName }] }),
  );
  await page.goto("/finances/accounts");
  const name = page.getByText(longName, { exact: true });
  await expect(name).toBeVisible();
  expect(
    await name.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  ).toBe(true);
  const label = await name.boundingBox();
  const action = await page
    .getByRole("button", { name: `Edytuj konto ${longName}` })
    .boundingBox();
  expect(
    label!.y + label!.height <= action!.y ||
      label!.x + label!.width <= action!.x,
  ).toBe(true);
});

test("day actions precede metrics in reading order", async ({ page }) => {
  const api = await fixtures(page);
  await page.goto("/today");
  await expect(
    page.getByRole("heading", { name: "Dzisiejszy plan" }),
  ).toBeVisible();
  expect(
    await page
      .getByRole("heading", { name: "Dzisiejszy plan" })
      .evaluate((el) => {
        const metric = [...document.querySelectorAll("p")].find(
          (p) => p.textContent === "Aktywne zadania",
        );
        return Boolean(
          metric &&
          el.compareDocumentPosition(metric) & Node.DOCUMENT_POSITION_FOLLOWING,
        );
      }),
  ).toBe(true);
  api.assertClean();
});

test("account identity stays readable independently of row actions", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/accounts");
  const name = page.getByText("Eurokonto", { exact: true });
  const edit = page.getByRole("button", { name: "Edytuj konto Eurokonto" });
  await expect(name).toBeVisible();
  const identity = await name.boundingBox();
  const action = await edit.boundingBox();
  expect(identity!.width).toBeGreaterThan(0);
  expect(
    await name.evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
  ).toBe(true);
  expect(
    identity!.y + identity!.height <= action!.y ||
      identity!.x + identity!.width <= action!.x,
  ).toBe(true);
  for (const label of [
    "Edytuj konto Eurokonto",
    "Dezaktywuj konto Eurokonto",
    "Usuń konto Eurokonto",
  ])
    expect(
      (await page.getByRole("button", { name: label }).boundingBox())!.height,
    ).toBeGreaterThanOrEqual(44);
  api.assertClean();
});

test("empty mobile calendar days stay compact and controls support touch", async ({
  page,
}) => {
  test.skip(page.viewportSize()!.width >= 1024, "Mobile agenda contract");
  const api = await fixtures(page);
  await page.goto("/calendar");
  const empty = page.getByText("Brak zaplanowanych pozycji.").first();
  await expect(empty).toBeVisible();
  const day = empty.locator("../..");
  expect((await day.boundingBox())!.height).toBeLessThanOrEqual(110);
  for (const label of [
    "Tydzień",
    "Miesiąc",
    "Poprzedni tydzień",
    "Następny tydzień",
  ])
    expect(
      (await page
        .getByRole("button", { name: label, exact: true })
        .boundingBox())!.height,
    ).toBeGreaterThanOrEqual(44);
  api.assertClean();
});

test("transaction form can recover from failed reference data without reloading", async ({
  page,
}) => {
  const api = await fixtures(page);
  let failed = true;
  await page.route("**/api/finance/accounts", async (route) => {
    if (failed)
      await route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    else await route.fallback();
  });
  await page.goto("/finances/transactions");
  await page.locator("summary").filter({ hasText: "Dodaj transakcję" }).click();
  const retry = page.getByRole("button", {
    name: "Ponów pobranie danych formularza",
  });
  await expect(retry).toBeVisible({ timeout: 15000 });
  failed = false;
  await retry.click();
  await expect(page.getByLabel("Typ", { exact: true })).toBeVisible();
  api.assertClean();
});

test("day plan sorts API blocks and marks only the active interval", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.clock.setFixedTime(new Date("2026-10-23T10:30:00Z"));
  await page.route("**/api/work/time-blocks?*", (route) =>
    route.fulfill({
      json: [
        {
          id: "later",
          title: "Następny blok",
          start_time: "2026-10-23T12:00:00Z",
          end_time: "2026-10-23T13:00:00Z",
          block_type: "shallow",
        },
        {
          id: "ended",
          title: "Zakończony blok",
          start_time: "2026-10-23T09:00:00Z",
          end_time: "2026-10-23T10:30:00Z",
          block_type: "deep_work",
        },
        {
          id: "active",
          title: "Bieżący blok",
          start_time: "2026-10-23T10:30:00Z",
          end_time: "2026-10-23T11:00:00Z",
          block_type: "deep_work",
        },
      ],
    }),
  );
  await page.goto("/today");
  const items = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Dzisiejszy plan" }) })
    .getByRole("listitem");
  await expect(items).toHaveCount(3);
  await expect(items.nth(0)).toContainText("Zakończony blok");
  await expect(items.nth(1)).toContainText("Bieżący blok");
  await expect(items.nth(2)).toContainText("Następny blok");
  await expect(page.getByText("Teraz", { exact: true })).toHaveCount(1);
  await expect(items.nth(1)).toContainText("Teraz");
  api.assertClean();
});
