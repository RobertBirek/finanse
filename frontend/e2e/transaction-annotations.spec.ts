import { expect, test } from "@playwright/test";
import { account, fixtures, transaction } from "./fixtures";

test("descriptive import edits preserve the original and money, allow free tags, and do not unlock loan categories", async ({
  page,
}, info) => {
  const base = await fixtures(page);
  let annotations = {
    display_description: null as string | null,
    original_description: "[actual:old] Oryginalny opis banku",
    note: null as string | null,
    tags: [] as { id: string; name: string }[],
    project_id: null as string | null,
    project_name: null as string | null,
    version: 0,
    context_snapshot: "a".repeat(64),
    limits: { display_description: 200, note: 5000, tag_name: 60, tags: 20 },
  };
  const current = () => ({
    ...transaction,
    source: "actual",
    description: annotations.original_description,
    effective_description:
      annotations.display_description || annotations.original_description,
    annotations,
  });
  const loan = {
    ...transaction,
    id: "loan",
    source: "loan_payment",
    description: "Rata pożyczki",
    effective_description: "Rata pożyczki",
  };
  const writes: {
    path: string;
    body: Record<string, unknown>;
    key?: string;
  }[] = [];
  await page.route("**/api/work/projects**", (route) =>
    route.fulfill({
      json: [{ id: "project", name: "Remont domu", status: "completed" }],
    }),
  );
  await page.route("**/api/finance/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname,
      method = route.request().method();
    if (method === "GET") {
      if (path.endsWith("/annotations"))
        return route.fulfill({ json: annotations });
      if (path === "/api/finance/tags")
        return route.fulfill({ json: [{ id: "vacation", name: "Wakacje" }] });
      if (path === "/api/finance/transactions/search")
        return route.fulfill({
          json: { items: [current(), loan], total: 2, limit: 25, offset: 0 },
        });
      if (path === `/api/finance/accounts/${account.id}/transactions`)
        return route.fulfill({ json: [current(), loan] });
      if (path.endsWith("/transactions/loan/categorization"))
        return route.fulfill({
          json: {
            transaction_id: "loan",
            eligibility: {
              allowed: false,
              reason_code: "protected_loan",
              message: "Płatność pożyczki jest chroniona.",
            },
            parts: [],
            amount_minor: 12345,
            currency: "EUR",
            version: 0,
            context_snapshot: "a".repeat(64),
            max_parts: 50,
          },
        });
      return route.fallback();
    }
    const body = route.request().postDataJSON();
    writes.push({
      path,
      body,
      key: route.request().headers()["idempotency-key"],
    });
    if (method === "PUT" && path.endsWith("/annotations")) {
      annotations = {
        ...annotations,
        display_description: body.display_description,
        note: body.note,
        tags: body.tags.map((name: string, index: number) => ({
          id: `tag-${index}`,
          name,
        })),
        project_id: body.project_id,
        project_name: body.project_id ? "Remont domu" : null,
        version: annotations.version + 1,
      };
      return route.fulfill({ json: annotations });
    }
    return route.fallback();
  });
  await page.goto("/finances/transactions");
  await page
    .getByRole("button", { name: "Opis i oznaczenia", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Opis i oznaczenia",
    exact: true,
  });
  await dialog.getByLabel("Nowy tag", { exact: true }).fill("Anulowany");
  await dialog.getByRole("button", { name: "Dodaj tag", exact: true }).click();
  await dialog.getByRole("button", { name: "Anuluj", exact: true }).click();
  expect(writes).toEqual([]);
  await page
    .getByRole("button", { name: "Opis i oznaczenia", exact: true })
    .first()
    .click();
  await expect(dialog.getByText("Anulowany", { exact: true })).toHaveCount(0);
  await expect(
    dialog.getByText(annotations.original_description, { exact: true }),
  ).toBeVisible();
  await dialog
    .getByLabel("Własny opis", { exact: true })
    .fill("Farba do pokoju");
  await dialog
    .getByLabel("Notatka", { exact: true })
    .fill("Paragon w segregatorze");
  await dialog.getByLabel("Nowy tag", { exact: true }).fill("Remont");
  await dialog.getByLabel("Nowy tag", { exact: true }).press("Enter");
  await dialog
    .getByRole("button", { name: "Dodaj tag Wakacje", exact: true })
    .click();
  await dialog.getByLabel("Projekt", { exact: true }).selectOption("project");
  expect(writes).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("annotation-draft.png"),
    fullPage: true,
  });
  await dialog
    .getByRole("button", { name: "Zapisz oznaczenia", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("Farba do pokoju", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator("p")
      .filter({ hasText: /^−123,45 EUR\s*Równowartość: 543,21 PLN$/ })
      .first(),
  ).toBeVisible();
  expect(writes[0].body).toEqual({
    display_description: "Farba do pokoju",
    note: "Paragon w segregatorze",
    tags: ["Remont", "Wakacje"],
    project_id: "project",
    expected_version: 0,
    expected_context_snapshot: "a".repeat(64),
  });
  expect(writes[0].key).toBeTruthy();
  expect(transaction.postings[0].id).toBe("p1");
  await page
    .getByRole("button", { name: "Zmień kategorie", exact: true })
    .nth(1)
    .click();
  await expect(
    page.getByText("Płatność pożyczki jest chroniona.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zamknij", exact: true }).click();
  await page
    .getByRole("button", { name: "Opis i oznaczenia", exact: true })
    .first()
    .click();
  await dialog.getByLabel("Własny opis", { exact: true }).fill("");
  await dialog
    .getByRole("button", { name: "Zapisz oznaczenia", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("[actual:old] Oryginalny opis banku", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(2);
  base.assertClean();
});
