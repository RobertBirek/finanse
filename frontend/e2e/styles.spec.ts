import { expect, test } from "@playwright/test";
import { fixtures } from "./fixtures";

test("compiled styles preserve the palette, form controls and responsive navigation", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/accounts");
  const form = page.getByRole("form", { name: "Nowe konto" });
  await expect(form).toBeVisible();
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(3, 7, 18)",
  );
  await expect(form).toHaveCSS("background-color", "rgb(17, 24, 39)");
  await expect(form).toHaveCSS("border-color", "rgb(31, 41, 55)");
  await expect(form).toHaveCSS("padding", "24px");
  await expect(form).toHaveCSS("border-radius", "12px");
  const input = form.getByLabel("Nazwa");
  await expect(input).toHaveCSS("background-color", "rgb(31, 41, 55)");
  await expect(input).toHaveCSS("padding", "10px 16px");
  const save = form.getByRole("button", { name: "Dodaj konto" });
  await expect(save).toHaveCSS("background-color", "rgb(1, 89, 161)");
  await expect(save).toHaveCSS("cursor", "pointer");
  await save.evaluate((element: HTMLButtonElement) => {
    element.disabled = true;
  });
  await expect(save).toHaveCSS("cursor", "not-allowed");

  const mobile = page.viewportSize()!.width < 1024;
  if (mobile) {
    await expect(
      page.getByRole("button", { name: "Otwórz menu aplikacji" }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Obszary aplikacji" }),
    ).not.toBeVisible();
  } else {
    await expect(
      page.getByRole("navigation", { name: "Obszary aplikacji" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Otwórz menu aplikacji" }),
    ).not.toBeVisible();
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  api.assertClean();
});

test("keyboard focus remains visible after the outline utility migration", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/accounts");
  const input = page
    .getByRole("form", { name: "Nowe konto" })
    .getByLabel("Nazwa");
  await input.focus();
  await expect(input).toBeFocused();
  await expect(input).toHaveCSS("outline-style", "solid");
  await expect(input).toHaveCSS("outline-width", "2px");
  await expect(input).toHaveCSS("outline-color", "rgb(124, 197, 252)");
  api.assertClean();
});

test("the native modal covers the viewport and centers its panel without parent spacing", async ({
  page,
}) => {
  const api = await fixtures(page);
  await page.goto("/finances/transactions");
  await page
    .getByRole("button", { name: "Szczegóły: Zakup kawy", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Szczegóły transakcji" });
  await expect(dialog).toBeVisible();
  const bounds = await dialog.boundingBox();
  const panel = await dialog.locator(":scope > div").boundingBox();
  const viewport = page.viewportSize()!;
  expect(bounds!.x).toBe(0);
  expect(bounds!.y).toBe(0);
  expect(bounds!.width).toBe(viewport.width);
  expect(bounds!.height).toBe(viewport.height);
  expect(
    Math.abs(panel!.y + panel!.height / 2 - viewport.height / 2),
  ).toBeLessThanOrEqual(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  api.assertClean();
});
