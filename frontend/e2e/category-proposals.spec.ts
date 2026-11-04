import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures, account, transaction } from "./fixtures";

async function proposalFixture(
  page: Page,
  mode: "mixed" | "unknown" | "new" = "mixed",
) {
  const base = await fixtures(page);
  const categories = [
    {
      id: "marker",
      name: "Do opisania",
      type: "expense",
      parent_id: null,
      is_active: true,
    },
    {
      id: "home",
      name: "Dom",
      type: "expense",
      parent_id: null,
      is_active: true,
    },
  ];
  const row = (id: string, description: string) => ({
    id,
    version: 1,
    status: "pending",
    transaction_id: id === "a" ? transaction.id : `txn-${id}`,
    description,
    amount_minor: 10000,
    currency: "PLN",
    decision: "existing_category",
    explanation: "Opis pasuje do kategorii Dom",
    confidence: "high",
    new_category: null,
    current_parts: [{ category_id: "marker", amount_minor: 10000 }],
    target_path: "Dom",
    eligible: true,
    blocked_reason: null,
    expires_at: "2026-11-11T12:00:00Z",
  });
  let rows =
    mode === "new"
      ? [
          {
            ...row("n", "Nowy zakup"),
            decision: "new_category",
            eligible: false,
            blocked_reason: "manual_category_required",
            new_category: {
              name: "Nowa grupa",
              parent_path: "Dom",
              explanation: "Do osobnego utworzenia",
            },
          },
        ]
      : [row("a", "Czynsz mieszkanie"), row("b", "Internet")];
  const writes: {
    path: string;
    body: Record<string, unknown>;
    key: string | undefined;
  }[] = [];
  const receipts = new Map<string, unknown>();
  let failed = false;
  let manual = false,
    approved = false,
    version = 0;
  const accountPosting = {
    ...transaction.postings[0],
    source_currency: "PLN",
    source_amount: 10000,
    base_amount_pln: 10000,
    fx_rate: 1,
    is_budget_impact: true,
  };
  const origin = () =>
    approved
      ? {
          origin: manual ? "manual" : "approved_llm",
          version,
          proposal_item_id: manual ? null : "a",
          display_description: "Czynsz mieszkanie",
          target_path: "Dom",
        }
      : null;
  const parts = () => [
    { category_id: approved ? "home" : "marker", amount_minor: 10000 },
  ];
  const context = () => ({
    transaction_id: transaction.id,
    eligibility: { allowed: true, reason_code: null, message: null },
    amount_minor: 10000,
    currency: "PLN",
    parts: parts(),
    version,
    source: approved ? "manual" : null,
    context_snapshot: "e".repeat(64),
    max_parts: 50,
    assignment_origin: origin(),
  });
  const current = () => ({
    ...transaction,
    description: "Czynsz mieszkanie",
    assignment_origin: origin(),
    postings: [
      accountPosting,
      {
        ...accountPosting,
        id: "category-p1",
        account_id: null,
        category_id: approved ? "home" : "marker",
        direction: "credit",
      },
    ],
  });
  await page.route("**/api/finance/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (req.method() === "GET") {
      if (path.endsWith("/categories"))
        return route.fulfill({ json: categories });
      if (path.endsWith("/accounts"))
        return route.fulfill({ json: [{ ...account, currency: "PLN" }] });
      if (path.endsWith("/categorization/proposals"))
        return route.fulfill({
          json: { items: rows, next_cursor: null, page_size: 20 },
        });
      if (path.endsWith("/transactions/search"))
        return route.fulfill({
          json: { items: [current()], total: 1, limit: 25, offset: 0 },
        });
      if (path.endsWith("/transactions"))
        return route.fulfill({ json: [current()] });
      if (path.endsWith("/categorization"))
        return route.fulfill({ json: context() });
      if (path === `/api/finance/transactions/${transaction.id}`)
        return route.fulfill({ json: current() });
      return route.fallback();
    }
    if (
      path.includes("/proposals/") ||
      path.endsWith("/categorization/preview") ||
      path.endsWith("/categorization/apply")
    ) {
      const body = req.postDataJSON();
      const key = req.headers()["idempotency-key"];
      writes.push({ path, body, key });
      if (path.endsWith("/categorization/preview"))
        return route.fulfill({
          json: {
            expected_version: version,
            preview_snapshot: "f".repeat(64),
            before_parts: parts(),
            after_parts: body.parts,
            target_paths: { marker: "Do opisania", home: "Dom" },
          },
        });
      if (path.endsWith("/categorization/apply")) {
        manual = true;
        version++;
        return route.fulfill({ json: context() });
      }
      const id = path.split("/").slice(-2)[0];
      if (path.endsWith("/preview"))
        return route.fulfill({
          json: {
            proposal_id: id,
            expected_version: 1,
            source_version: 0,
            context_snapshot: "e".repeat(64),
            preview_snapshot: id.repeat(64),
            amount_minor: 10000,
            currency: "PLN",
            before_parts: [{ category_id: "marker", amount_minor: 10000 }],
            after_parts: [{ category_id: "home", amount_minor: 10000 }],
            target_path: "Dom",
            explanation: "Opis pasuje do kategorii Dom",
            confidence: "high",
            expires_at: "2026-11-11T12:00:00Z",
          },
        });
      if (key && receipts.has(key))
        return route.fulfill({ json: receipts.get(key) });
      if (id === "b" && mode === "mixed")
        return route.fulfill({
          status: 409,
          json: { detail: "Source changed" },
        });
      approved = true;
      version = 1;
      rows = rows.filter((r) => r.id !== id);
      const result = {
        proposal_id: id,
        version: 2,
        status: "approved",
        context: context(),
      };
      if (key) receipts.set(key, result);
      if (mode === "unknown" && !failed) {
        failed = true;
        return route.abort("connectionreset");
      }
      return route.fulfill({ json: result });
    }
    return route.fallback();
  });
  return { base, writes };
}

for (const width of [375, 1440]) {
  test(`reviewed AI selected items and partial result ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await proposalFixture(page);
    await page.goto("/finances/proposals?month=2&year=2026");
    const a = page.getByLabel("Wybierz Czynsz mieszkanie");
    await expect(a).not.toBeChecked();
    await a.focus();
    await page.keyboard.press("Space");
    await page.getByLabel("Wybierz Internet").check();
    await page.getByRole("button", { name: "Przejrzyj wybrane (2)" }).click();
    await expect(
      page.getByRole("button", { name: "Zatwierdź wybrane (2)" }),
    ).toBeVisible();
    expect(f.writes.filter((w) => w.path.endsWith("/apply"))).toHaveLength(0);
    expect(
      (await new AxeBuilder({ page }).include("main").analyze()).violations,
    ).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: info.outputPath("reviewed-proposals.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "Zatwierdź wybrane (2)" }).click();
    await expect(page.getByText("Zatwierdzono", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Dane zmieniły się — sprawdź ponownie"),
    ).toBeVisible();
    const applies = f.writes.filter((w) => w.path.endsWith("/apply"));
    expect(applies).toHaveLength(2);
    expect(applies.every((w) => !!w.key)).toBeTruthy();
    expect(applies[0].body).toEqual({
      expected_version: 1,
      preview_snapshot: "a".repeat(64),
      confirmed: true,
    });
    f.base.assertClean();
  });
  test(`uncertain review retries same receipt key ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await proposalFixture(page, "unknown");
    await page.goto("/finances/proposals");
    await page.getByLabel("Wybierz Czynsz mieszkanie").check();
    await page.getByLabel("Wybierz Internet").check();
    await page.getByRole("button", { name: "Przejrzyj wybrane (2)" }).click();
    await page.getByRole("button", { name: "Zatwierdź wybrane (2)" }).click();
    await expect(
      page.getByRole("button", { name: "Ponów niedokończone" }),
    ).toBeVisible();
    expect(f.writes.filter((w) => w.path.endsWith("/apply"))).toHaveLength(1);
    await page.getByRole("button", { name: "Ponów niedokończone" }).click();
    await expect(page.getByText("Zatwierdzono", { exact: true })).toHaveCount(
      2,
    );
    const applies = f.writes.filter((w) => w.path.endsWith("/apply"));
    expect(applies).toHaveLength(3);
    expect(applies[0]).toEqual(applies[1]);
    expect(
      f.writes.some((w) => w.path === "/api/finance/transactions"),
    ).toBeFalsy();
    f.base.assertClean();
  });
  test(`new category has a separate manual path ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await proposalFixture(page, "new");
    await page.goto("/finances/proposals");
    await expect(
      page.getByRole("link", { name: "Utwórz kategorię osobno" }),
    ).toHaveAttribute("href", "/settings/finances/categories");
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Przejrzyj wybrane (0)" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Przypisz ręcznie" }).click();
    await expect(
      page.getByRole("dialog", { name: "Kategorie wydatku", exact: true }),
    ).toBeVisible();
    expect(f.writes).toHaveLength(0);
    f.base.assertClean();
  });
  test(`manual confirmation replaces approved AI origin ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const f = await proposalFixture(page);
    await page.goto("/finances/proposals");
    await page.getByLabel("Wybierz Czynsz mieszkanie").check();
    await page.getByRole("button", { name: "Przejrzyj wybrane (1)" }).click();
    await page.getByRole("button", { name: "Zatwierdź wybrane (1)" }).click();
    await expect(page.getByText("Zatwierdzono", { exact: true })).toBeVisible();
    await page.goto("/finances/transactions");
    await expect(
      page.getByText("Kategoria z propozycji AI — zatwierdzona przez Ciebie"),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Zmień kategorie", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Kategorie wydatku",
      exact: true,
    });
    await dialog.getByRole("button", { name: "Sprawdź podział" }).click();
    await dialog.getByRole("button", { name: "Zatwierdź podział" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(
      page.getByText("Ręcznie zatwierdzona kategoria"),
    ).toBeVisible();
    f.base.assertClean();
  });
}
