import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";

for (const [path, title] of [
  ["/finances/transactions", "Transakcje"],
  ["/documents", "Dokumenty"],
  ["/settings/ai", "Ustawienia AI"],
  ["/settings", "Ustawienia"],
  ["/calendar", "Kalendarz"],
  ["/settings/finances/accounts", "Konta i rachunki"],
] as const) {
  test(`${title}: obszar roboczy wypełnia dostępną szerokość`, async ({
    page,
  }, info) => {
    if (info.project.name === "desktop") {
      await page.setViewportSize({ width: 1920, height: 1080 });
    }
    await fixtures(page);
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible();
    const geometry = await page.locator("#main-content").evaluate((element) => {
      const style = getComputedStyle(element);
      const available =
        element.clientWidth -
        parseFloat(style.paddingLeft) -
        parseFloat(style.paddingRight);
      return {
        missing:
          available - element.firstElementChild!.getBoundingClientRect().width,
        overflow: element.scrollWidth - element.clientWidth,
      };
    });
    expect(Math.abs(geometry.missing)).toBeLessThanOrEqual(1);
    expect(geometry.overflow).toBeLessThanOrEqual(1);
  });
}

test("ustawienia finansów mają jeden nagłówek bieżącego widoku", async ({
  page,
}) => {
  await fixtures(page);
  await page.goto("/settings/finances/categories");
  const headings = page.getByRole("heading", { level: 1 });
  await expect(headings).toHaveText(["Kategorie"]);
});

for (const [path, label] of [
  ["/inbox", "Dzisiaj"],
  ["/calendar", "Dzisiaj"],
  ["/documents", "Dokumenty"],
] as const) {
  test(`nawigacja mobilna wskazuje obszar dla ${path}`, async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "mobile", "Dolna nawigacja mobilna");
    await fixtures(page);
    await page.route(
      (url) => url.pathname === "/api/inbox/items",
      (route) => route.fulfill({ json: [] }),
    );
    await page.goto(path);
    const navigation = page.getByRole("navigation", {
      name: "Nawigacja mobilna",
    });
    await expect(
      navigation.getByRole("link", { name: label, exact: true }),
    ).toHaveAttribute("aria-current", /^(page|location)$/);
    await expect(navigation.locator("[aria-current]")).toHaveCount(1);
  });
}

test("sekcja Dzisiaj daje bezpośredni dostęp do Inboxu i Kalendarza na telefonie", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "mobile", "Nawigacja sekcji na telefonie");
  await fixtures(page);
  await page.route(
    (url) => url.pathname === "/api/inbox/items",
    (route) => route.fulfill({ json: [] }),
  );
  await page.goto("/inbox");
  const subnav = page.getByRole("navigation", {
    name: "Widoki sekcji Dzisiaj",
  });
  await expect(subnav.getByRole("link", { name: "Inbox" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await subnav.getByRole("link", { name: "Kalendarz" }).click();
  await expect(subnav.getByRole("link", { name: "Kalendarz" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("jasny kalendarz zachowuje wymagany kontrast tekstu", async ({ page }) => {
  await fixtures(page);
  await page.goto("/calendar");
  await expect(page.getByRole("heading", { name: "Kalendarz" })).toBeVisible();
  const result = await new AxeBuilder({ page })
    .withRules(["color-contrast"])
    .analyze();
  expect(result.violations).toEqual([]);
});

test("podpowiedź akcji dokumentu zamyka się klawiszem Escape bez utraty fokusu", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "Fokus i wskaźnik desktopowy");
  await fixtures(page);
  await page.goto("/documents");
  const action = page.getByRole("button", {
    name: "Archiwizuj dokument: Faktura.pdf",
  });
  const tooltip = page.getByText("Archiwizuj dokument", { exact: true });
  await action.focus();
  await expect(tooltip).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(tooltip).toBeHidden();
  await expect(action).toBeFocused();
});

test("podpowiedź dokumentu jest dostępna pod kursorem i znika po jego odsunięciu", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "Najechanie kursorem");
  await fixtures(page);
  await page.goto("/documents");
  await page
    .getByRole("button", { name: "Archiwizuj dokument: Faktura.pdf" })
    .hover();
  const tooltip = page.getByText("Archiwizuj dokument", { exact: true });
  await expect(tooltip).toBeVisible();
  await tooltip.hover();
  await expect(tooltip).toBeVisible();
  await page.getByRole("heading", { name: "Dokumenty" }).hover();
  await expect(tooltip).toBeHidden();
});

test("mysz otwiera Więcej bez zasłaniania akcji usunięcia", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "Najechanie kursorem");
  await fixtures(page);
  await page.goto("/finances/transactions");
  const more = page.getByRole("button", { name: "Więcej: Zakup kawy" });
  const tooltip = more.locator("xpath=..").getByText("Więcej", { exact: true });
  await more.hover();
  await expect(tooltip).toBeVisible();
  await more.click();
  await expect(tooltip).toBeHidden();
  await page
    .getByRole("button", { name: "Usuń transakcję", exact: true })
    .click();
  const confirmation = page.getByRole("dialog", { name: "Usuń transakcję" });
  await expect(confirmation).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "Anuluj" }),
  ).toBeFocused();
});

test("dotyk otwiera Więcej i pozwala potwierdzić usunięcie", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "mobile", "Wymaga ekranu dotykowego");
  await fixtures(page);
  await page.goto("/finances/transactions");
  await page.getByRole("button", { name: "Więcej: Zakup kawy" }).tap();
  await page
    .getByRole("button", { name: "Usuń transakcję", exact: true })
    .tap();
  await expect(
    page.getByRole("dialog", { name: "Usuń transakcję" }),
  ).toBeVisible();
});

test("podpowiedź Więcej zamyka się Escape bez utraty fokusu", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "Fokus i wskaźnik desktopowy");
  await fixtures(page);
  await page.goto("/finances/transactions");
  const more = page.getByRole("button", { name: "Więcej: Zakup kawy" });
  const tooltip = more.locator("xpath=..").getByText("Więcej", { exact: true });
  await more.focus();
  await expect(tooltip).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(tooltip).toBeHidden();
  await expect(more).toBeFocused();
});

test("szczegóły projektu odróżniają niedostępność od braku projektu i pozwalają ponowić odczyt", async ({
  page,
}) => {
  await fixtures(page);
  let unavailable = true;
  await page.route("**/api/work/projects/ui-audit", (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: "Fixture unavailable" } })
      : route.fulfill({
          json: {
            id: "ui-audit",
            name: "Projekt audytowy",
            description: null,
            status: "active",
            deadline: null,
          },
        }),
  );
  await page.goto("/projects/ui-audit");
  await expect(page.getByRole("alert")).toContainText(
    "Nie udało się pobrać projektu",
  );
  unavailable = false;
  await page.getByRole("button", { name: "Spróbuj ponownie" }).click();
  await expect(
    page.getByRole("heading", { name: "Projekt audytowy", level: 1 }),
  ).toBeVisible();
});

test("Inbox odróżnia pusty filtr od pustej skrzynki", async ({ page }) => {
  await fixtures(page);
  await page.route(
    (url) => url.pathname === "/api/inbox/items",
    (route) => route.fulfill({ json: [] }),
  );
  await page.goto("/inbox");
  await page.getByRole("button", { name: "Przetworzone", exact: true }).click();
  await expect(page.getByText("Brak przetworzonych wpisów.")).toBeVisible();
  await page.getByRole("button", { name: "Pokaż wszystkie wpisy" }).click();
  await expect(page.getByText("Nie ma jeszcze żadnych wpisów.")).toBeVisible();
});

test("usunięcie transakcji jest opisane w Więcej i wymaga osobnego potwierdzenia", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/transactions");
  const more = page.getByRole("button", { name: "Więcej: Zakup kawy" });
  await expect(
    page.getByRole("button", { name: "Usuń", exact: true }),
  ).toBeHidden();
  await more.click();
  await page
    .getByRole("button", { name: "Usuń transakcję", exact: true })
    .click();
  const confirmation = page.getByRole("dialog", { name: "Usuń transakcję" });
  await expect(confirmation).toContainText("Zakup kawy");
  await expect(
    confirmation.getByRole("button", { name: "Anuluj" }),
  ).toBeFocused();
  await confirmation.getByRole("button", { name: "Anuluj" }).click();
  await expect(confirmation).toBeHidden();
  await expect(more).toBeFocused();
  expect(api.mutations).toEqual([]);
  api.assertClean();
});

test("oczekujące usunięcie transakcji pozostawia potwierdzenie i pokazuje błąd w oknie", async ({
  page,
}) => {
  await fixtures(page);
  let respond!: () => void;
  const waitForResponse = new Promise<void>((resolve) => {
    respond = resolve;
  });
  let requests = 0;
  await page.route("**/api/finance/transactions/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    requests += 1;
    await waitForResponse;
    await route.fulfill({
      status: 409,
      json: { detail: "Transakcja ma powiązania." },
    });
  });
  await page.goto("/finances/transactions");
  await page.getByRole("button", { name: "Więcej: Zakup kawy" }).click();
  await page
    .getByRole("button", { name: "Usuń transakcję", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Usuń transakcję" });
  try {
    await dialog.getByRole("button", { name: "Usuń transakcję" }).click();
    await expect(dialog).toHaveAttribute("aria-busy", "true");
    await expect(dialog.getByRole("status")).toHaveText("Usuwanie transakcji…");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
  } finally {
    respond();
  }
  await expect(dialog.getByRole("alert")).toContainText(
    "Transakcja ma powiązania.",
  );
  await dialog.getByRole("button", { name: "Anuluj" }).click();
  expect(requests).toBe(1);
});

test("zamykanie formularza używa ikony z dostępną nazwą i zachowuje główną akcję", async ({
  page,
}) => {
  await fixtures(page);
  await page.goto("/finances/transactions");
  const add = page.getByRole("button", { name: /Dodaj transakcję/ });
  await expect(add).toContainText("Dodaj transakcję");
  await add.click();
  const dialog = page.getByRole("dialog", { name: "Dodaj transakcję" });
  const close = dialog.getByRole("button", { name: "Zamknij formularz" });
  await expect(close).toHaveText("");
  await expect(close).toHaveCSS("height", "44px");
  await close.click();
  await expect(dialog).toBeHidden();
  await expect(add).toBeFocused();
});

test("pole wyszukiwania nie rozciąga się na całą szerokość monitora", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await fixtures(page);
  await page.goto("/finances/transactions");
  const field = page.getByRole("searchbox", {
    name: "Szukaj po opisie, koncie lub kategorii",
  });
  await expect(field).toBeVisible();
  expect((await field.boundingBox())!.width).toBeLessThanOrEqual(736);
});

test("na ekranie dotykowym status dokumentu jest czytelny bez podpowiedzi", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "mobile", "Ekran dotykowy");
  await page.setViewportSize({ width: 320, height: 760 });
  await fixtures(page);
  await page.goto("/documents");
  const document = page
    .getByRole("listitem")
    .filter({ hasText: "Faktura.pdf" });
  await expect(document.getByText(/^Odczyt:/)).toBeVisible();
  await expect(document.getByText(/^Finanse:/)).toBeVisible();
});
