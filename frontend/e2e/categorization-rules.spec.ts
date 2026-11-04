import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";

for (const width of [375, 1440])
  test(`approved exact rules settings at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const base = await fixtures(page);
    const categories = [
      {
        id: "marker",
        name: "Do opisania",
        parent_id: null,
        type: "expense",
        is_active: true,
      },
      {
        id: "home",
        name: "Dom",
        parent_id: null,
        type: "expense",
        is_active: true,
      },
    ];
    let policy = {
      version: 0,
      uncategorized_category_id: null as string | null,
      rules_enabled: false,
      max_description_chars: 500,
    };
    let rules: Record<string, unknown>[] = [];
    const writes: {
      path: string;
      key: string | undefined;
      body: Record<string, unknown>;
    }[] = [];
    await page.route("**/api/finance/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const method = route.request().method();
      if (path.endsWith("/categories"))
        return route.fulfill({ json: categories });
      if (path.endsWith("/categorization/settings") && method === "GET")
        return route.fulfill({ json: policy });
      if (path.endsWith("/categorization/rules") && method === "GET")
        return route.fulfill({ json: rules });
      if (path.includes("/categorization/") && method !== "GET") {
        const body = route.request().postDataJSON();
        writes.push({
          path,
          body,
          key: route.request().headers()["idempotency-key"],
        });
        if (path.endsWith("/settings")) {
          policy = { ...policy, ...body, version: policy.version + 1 };
          return route.fulfill({ json: policy });
        }
        if (path.endsWith("/preview"))
          return route.fulfill({
            json: {
              preview_snapshot: "a".repeat(64),
              grant: {
                display_description: "CZYNSZ mieszkanie",
                normalized_description_exact: "czynsz mieszkanie",
                target_path: "Dom",
                marker_id: "marker",
                scope: "future_manual_pln_only",
              },
            },
          });
        if (path.endsWith("/approve")) {
          rules = [{ ...rules[0], state: "active", approved_version: 1 }];
          return route.fulfill({ json: rules[0] });
        }
        if (path.endsWith("/pause")) {
          rules = [{ ...rules[0], state: "paused", version: 2 }];
          return route.fulfill({ json: rules[0] });
        }
        rules = [
          {
            id: "r1",
            version: 1,
            state: "draft",
            approved_version: null,
            display_description: body.display_description,
            normalized_description_exact: "czynsz mieszkanie",
            target_category_id: "home",
          },
        ];
        return route.fulfill({ status: 201, json: rules[0] });
      }
      return route.fallback();
    });
    await page.goto("https://ui.test.invalid/settings/finances/categorization");
    await expect(
      page.getByRole("heading", { name: "Kategoryzacja", exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Kategoria techniczna", { exact: true })
      .selectOption("marker");
    await page.getByLabel("Włącz zatwierdzone reguły").check();
    await expect(
      page.getByRole("button", { name: "Zapisz ustawienia" }),
    ).toBeDisabled();
    await page.getByLabel(/Potwierdzam zakres przyszłych wydatków/).check();
    await page.getByRole("button", { name: "Zapisz ustawienia" }).click();
    await expect(page.getByText("Ustawienia zapisane.")).toBeVisible();
    await page.getByRole("button", { name: "Nowa reguła" }).click();
    const dialog = page.getByRole("dialog", { name: "Reguła kategoryzacji" });
    await dialog
      .getByLabel("Dokładny opis transakcji")
      .fill("CZYNSZ mieszkanie");
    await dialog
      .getByLabel("Kategoria docelowa", { exact: true })
      .selectOption("home");
    await dialog.getByRole("button", { name: "Zapisz szkic" }).click();
    await expect(
      dialog.getByRole("button", { name: "Podgląd reguły" }),
    ).toBeEnabled();
    await dialog.getByRole("button", { name: "Podgląd reguły" }).click();
    await expect(
      dialog.getByText("czynsz mieszkanie", { exact: true }),
    ).toBeVisible();
    await dialog.getByLabel(/Zatwierdzam dokładne dopasowanie/).check();
    await dialog
      .getByRole("button", { name: "Zatwierdź dla przyszłych wydatków" })
      .click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: "Wstrzymaj" }).click();
    await expect(page.getByText(/Wstrzymana · wersja 2/)).toBeVisible();
    expect(
      writes.filter((w) => !w.path.endsWith("/preview")).every((w) => !!w.key),
    ).toBeTruthy();
    expect(writes.find((w) => w.path.endsWith("/approve"))?.body).toMatchObject(
      { expected_version: 1, confirm_future_only: true },
    );
    expect(writes.some((w) => w.path.includes("/transactions"))).toBeFalsy();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    expect(
      (await new AxeBuilder({ page }).include("main").analyze()).violations,
    ).toEqual([]);
    base.assertClean();
  });
