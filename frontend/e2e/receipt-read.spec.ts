import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { fixtures } from "./fixtures";
import {
  categories,
  context,
  preview,
} from "../src/components/finance/receipts/receiptTestData";
import {
  readContext,
  readJob,
  exportPreview,
  readResult,
} from "../src/components/finance/receipts/receiptReadTestData";
import type { ReceiptItemsContext, ReceiptBody } from "../src/api/receiptItems";
import type {
  ReceiptReadJob,
  ReceiptReadEvidence,
} from "../src/api/receiptRead";

async function setup(page: Page, mode = "ready") {
  const base = await fixtures(page);
  await page.route("**/api/documents/photo/{preview,original}", (route) =>
    route.fulfill({
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2S5sAAAAASUVORK5CYII=",
        "base64",
      ),
    }),
  );
  let state: ReceiptItemsContext = {
    ...context(0),
    draft: null,
    approved: null,
    calculation: null,
  };
  let job: ReceiptReadJob | null = null;
  const receipts = new Map<string, unknown>(),
    writes: { action: string; body: Record<string, unknown>; key?: string }[] =
      [],
    unknown: string[] = [];
  let starts = 0,
    imports = 0,
    dispatches = 0,
    payments = 0,
    lost = false;
  const proposal = structuredClone(readResult.proposal);
  proposal.body.store_id = null;
  proposal.body.store_version = null;
  for (const line of proposal.body.lines) {
    line.category_id = null;
    line.hint = null;
  }
  const warning = {
    key: "source/missing_rows",
    code: "missing_rows",
    line_index: null,
    discount_index: null,
    message: "Sprawdź brakujące produkty na zdjęciu.",
    requires_ack: true,
  };
  const evidence: ReceiptReadEvidence = {
    extraction_id: "extraction",
    extraction_sha256: "c".repeat(64),
    job_id: "job",
    source_document_id: "photo",
    source_sha256: "a".repeat(64),
    line_map: {
      a: {
        source_index: 0,
        source_text: "MLEKO 80,00",
        original_field_sha256: {},
        edited_fields: [],
      },
      b: {
        source_index: 1,
        source_text: "PLYN 20,00",
        original_field_sha256: {},
        edited_fields: [],
      },
    },
    discount_map: {},
    pending_problems: mode === "partial" ? [warning] : [],
    acknowledgements: {},
  };
  const bill = {
    id: "bill",
    kind: "receipt",
    supplier_name: "Zakup w sklepie",
    supplier_tax_id: null,
    number: null,
    issue_date: "2026-11-04",
    sale_date: null,
    due_date: null,
    payee_iban: null,
    description: "Paragon ze zdjęcia",
    category_id: null,
    payment_account_id: null,
    total_minor: 9000,
    currency: "PLN",
    declaration: "declared_paid",
    lifecycle: "active",
    review: "approved",
    version: 1,
    paid_minor: 9000,
    remaining_minor: 0,
    reconciliation: "full",
    sources: [{ id: "photo", document_id: "photo", name: "Mój paragon.png" }],
    allocations: [
      { id: "allocation", posting_id: "account-posting", amount_minor: 9000 },
    ],
    extraction_revision_id: null,
    coverage: null,
    recurring_decision: null,
    forecast_exclusion_reasons: [],
  };
  await page.route("**/api/finance/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (path === "/api/finance/categories")
      return route.fulfill({ json: categories });
    if (path === "/api/finance/receipt-stores")
      return route.fulfill({
        json: {
          items: [
            { id: "store", name: "Sklep osiedlowy", version: 1, active: true },
          ],
          next_cursor: null,
        },
      });
    if (path === "/api/finance/bills")
      return route.fulfill({
        json: { items: [bill], total: 1, limit: 25, offset: 0 },
      });
    if (path === "/api/finance/bills/bill")
      return route.fulfill({ json: bill });
    const prefix = "/api/finance/bills/bill/items";
    if (!path.startsWith(prefix)) return route.fallback();
    const action = path.slice(prefix.length + 1);
    if (req.method() === "GET") {
      if (!action) return route.fulfill({ json: state });
      if (action === "payment")
        return route.fulfill({
          json: { allowed: true, last_application: null, blocked_reason: null },
        });
      if (action === "history")
        return route.fulfill({
          json: {
            items: [],
            match_kind: "none",
            conflict: false,
            has_more: false,
            history_incomplete: false,
          },
        });
      if (action === "reads/context")
        return route.fulfill({
          json: { ...readContext, state_version: state.state_version },
        });
      if (action === "reads")
        return route.fulfill({
          json: { items: job ? [job] : [], next_cursor: null },
        });
      if (action === "reads/job") return route.fulfill({ json: job });
      if (action === "reads/job/result")
        return route.fulfill({
          json: {
            ...readResult,
            job,
            quality: mode === "partial" ? "partial" : "complete",
            proposal: {
              ...proposal,
              problems: mode === "partial" ? [warning] : [],
            },
          },
        });
    }
    const data = req.postDataJSON() as Record<string, unknown>,
      key = req.headers()["idempotency-key"];
    writes.push({ action, body: data, key });
    if (action === "read-export-preview")
      return route.fulfill({
        json: { ...exportPreview, reread_of_job_id: data.reread_of_job_id },
      });
    if (action === "read-import-preview")
      return route.fulfill({
        json: {
          job_id: "job",
          extraction_id: "extraction",
          payload_sha256: "c".repeat(64),
          bill_version: 1,
          state_version: state.state_version,
          import_snapshot: "e".repeat(64),
          will_replace_draft: !!state.draft,
          proposal,
        },
      });
    if (action === "payment-preview")
      return route.fulfill({
        json: {
          ...preview,
          expected_state_version: state.state_version,
          approved_revision_id: state.approved!.id,
        },
      });
    if (!key) {
      unknown.push(action);
      return route.fulfill({ status: 422, json: { detail: "key missing" } });
    }
    if (receipts.has(key)) return route.fulfill({ json: receipts.get(key) });
    let response: unknown;
    if (action === "read-start") {
      starts++;
      job = {
        ...readJob,
        state:
          mode === "cancel" || mode === "cancel-race"
            ? "pending"
            : mode === "lost"
              ? "unknown"
              : "succeeded",
        can_cancel: mode === "cancel" || mode === "cancel-race",
        poll_after_ms:
          mode === "cancel" || mode === "cancel-race" ? 30000 : null,
      };
      if (mode !== "cancel" && mode !== "cancel-race") dispatches++;
      response = structuredClone(job);
    } else if (action === "reads/job/cancel") {
      if (mode === "cancel-race") {
        dispatches++;
        job = {
          ...job!,
          state: "dispatched",
          dispatched: true,
          can_cancel: false,
        };
        return route.fulfill({
          status: 409,
          json: { code: "read_dispatched" },
        });
      }
      job = {
        ...job!,
        state: "cancelled",
        can_cancel: false,
        poll_after_ms: null,
      };
      response = job;
    } else if (action === "read-import") {
      imports++;
      state = {
        ...state,
        state_version: state.state_version + 1,
        draft: {
          ...context().draft!,
          body: structuredClone(proposal.body),
          current: false,
          evidence: structuredClone(evidence),
        },
      };
      response = state;
    } else if (action === "draft") {
      const updated = data.body as ReceiptBody;
      state = {
        ...state,
        state_version: state.state_version + 1,
        draft: {
          ...state.draft!,
          id: `draft-${state.state_version + 1}`,
          body: updated,
        },
      };
      const total =
        updated.lines.reduce((a, l) => a + (l.amount_minor ?? 0), 0) -
        updated.discounts.reduce((a, d) => a + (d.amount_minor ?? 0), 0);
      const reviewed = (
        data.extraction_review as
          { acknowledged_problem_keys: string[] } | undefined
      )?.acknowledged_problem_keys.includes(warning.key);
      if (state.draft!.evidence && mode === "partial") {
        state.draft!.evidence!.pending_problems = reviewed ? [] : [warning];
        state.draft!.evidence!.acknowledgements = reviewed
          ? { [warning.key]: "bound-to-body" }
          : {};
      }
      state.calculation = {
        ...context().calculation!,
        net_total_minor: total,
        difference_minor: total - 9000,
        problems:
          total === 9000
            ? []
            : [{ code: "mismatch", message: "Suma różni się od paragonu." }],
      };
      state.draft!.current =
        total === 9000 &&
        !!updated.store_id &&
        updated.lines.every((l) => !!l.category_id) &&
        (mode !== "partial" || !!reviewed);
      response = state;
    } else if (action === "approve") {
      expect(state.draft!.current).toBe(true);
      state = {
        ...state,
        state_version: state.state_version + 1,
        approved: { ...state.draft!, kind: "approved", id: "approved" },
        draft: null,
      };
      response = state;
    } else if (action === "payment-apply") {
      payments++;
      response = {
        receipt_id: "payment-receipt",
        state_version: ++state.state_version,
        revision_id: "approved",
      };
    } else {
      unknown.push(action);
      return route.fulfill({ status: 422, json: { detail: "unregistered" } });
    }
    receipts.set(key, structuredClone(response));
    if (action === "read-start" && mode === "lost" && !lost) {
      lost = true;
      return route.abort("failed");
    }
    return route.fulfill({ json: response });
  });
  return {
    writes,
    get dispatches() {
      return dispatches;
    },
    get starts() {
      return starts;
    },
    get imports() {
      return imports;
    },
    get payments() {
      return payments;
    },
    assertClean() {
      expect(unknown).toEqual([]);
      base.assertClean();
    },
  };
}
async function open(page: Page) {
  await page.goto("/finances/documents?bill=bill");
  await page
    .getByRole("button", { name: "Produkty i kategorie", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Zdjęcie paragonu" })
    .selectOption("photo");
}
async function send(page: Page) {
  await page
    .getByRole("button", { name: "Odczytaj produkty ze zdjęcia", exact: true })
    .click();
  await expect(page.getByText(/całego obrazu/)).toBeVisible();
  await page
    .getByRole("button", { name: "Wyślij zdjęcie i odczytaj produkty" })
    .click();
}
async function adopt(page: Page) {
  await page
    .getByRole("button", { name: "Użyj w szkicu", exact: true })
    .click();
  await page.getByRole("button", { name: "Zastąp szkic odczytem" }).click();
  await expect(page.getByLabel("Produkt 1", { exact: true })).toHaveValue(
    "Mleko",
  );
}
async function categoriesFor(page: Page) {
  await page
    .getByRole("combobox", { name: "Sklep", exact: true })
    .selectOption("store");
  await page
    .getByLabel("Kategoria produktu 1", { exact: true })
    .selectOption("food");
  await page
    .getByLabel("Kategoria produktu 2", { exact: true })
    .selectOption("home");
}

test("receipt read explicit adoption still needs two separate financial confirmations", async ({
  page,
}, info) => {
  const f = await setup(page);
  await open(page);
  expect(f.dispatches).toBe(0);
  await send(page);
  await expect(
    page.getByRole("button", { name: "Użyj w szkicu" }),
  ).toBeVisible();
  expect(f.imports).toBe(0);
  await adopt(page);
  await categoriesFor(page);
  await page.getByRole("button", { name: "Zapisz robocze" }).click();
  await page
    .getByRole("button", { name: "Zatwierdź pozycje", exact: true })
    .click();
  expect(f.payments).toBe(0);
  await page.getByRole("button", { name: "Sprawdź podział płatności" }).click();
  await expect(page.getByText(/72,00/).first()).toBeVisible();
  await expect(page.getByText(/18,00/).first()).toBeVisible();
  expect(f.payments).toBe(0);
  await page
    .getByRole("button", { name: "Zatwierdź podział", exact: true })
    .click();
  await expect(page.getByText(/Podział zatwierdzony/)).toBeVisible();
  expect(f.dispatches).toBe(1);
  expect(f.imports).toBe(1);
  expect(f.payments).toBe(1);
  await page.screenshot({
    path: info.outputPath("receipt-read.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze())
      .violations,
  ).toEqual([]);
  f.assertClean();
});
test("receipt unknown start replays exact consent and key, status GET never sends again", async ({
  page,
}) => {
  const f = await setup(page, "lost");
  await open(page);
  await send(page);
  await expect(
    page.getByRole("button", { name: "Sprawdź tę samą próbę" }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: "Produkty i kategorie", exact: true })
    .click();
  await page.getByRole("button", { name: "Sprawdź tę samą próbę" }).click();
  await expect(
    page.getByRole("button", { name: "Sprawdź wynik" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sprawdź wynik" }).click();
  const starts = f.writes.filter((w) => w.action === "read-start");
  expect(starts).toHaveLength(2);
  expect(starts[0]).toEqual(starts[1]);
  expect(f.starts).toBe(1);
  expect(f.dispatches).toBe(1);
  expect(f.imports).toBe(0);
  await page
    .getByRole("button", { name: "Odczytaj ponownie — możliwy kolejny koszt" })
    .click();
  await expect(
    page.getByRole("button", { name: "Wyślij zdjęcie i odczytaj produkty" }),
  ).toBeVisible();
  expect(f.dispatches).toBe(1);
  f.assertClean();
});
for (const mode of ["cancel", "cancel-race"])
  test(`receipt cancellation ${mode} respects the dispatch boundary`, async ({
    page,
  }) => {
    const f = await setup(page, mode);
    await open(page);
    await send(page);
    await page
      .getByRole("button", { name: "Anuluj niewysłany odczyt" })
      .click();
    await expect(
      page.getByRole("status").filter({
        hasText:
          mode === "cancel" ? "Anulowano przed wysyłką" : "nie można cofnąć",
      }),
    ).toBeVisible();
    expect(f.dispatches).toBe(mode === "cancel" ? 0 : 1);
    expect(f.imports).toBe(0);
    expect(f.payments).toBe(0);
    f.assertClean();
  });
test("receipt partial source warnings survive a matching sum until human review", async ({
  page,
}) => {
  const f = await setup(page, "partial");
  await open(page);
  await send(page);
  await adopt(page);
  await categoriesFor(page);
  await page.getByRole("button", { name: "Zapisz robocze" }).click();
  await expect(
    page.getByRole("button", { name: "Zatwierdź pozycje", exact: true }),
  ).toBeDisabled();
  await page.getByLabel(/Sprawdzono: Sprawdź brakujące/).check();
  await page.getByLabel("Produkt 1", { exact: true }).fill("Poprawiona nazwa");
  await expect(
    page.getByLabel(/Sprawdzono: Sprawdź brakujące/),
  ).not.toBeChecked();
  await page.getByLabel(/Sprawdzono: Sprawdź brakujące/).check();
  await page.getByRole("button", { name: "Zapisz robocze" }).click();
  await expect(
    page.getByRole("button", { name: "Zatwierdź pozycje", exact: true }),
  ).toBeEnabled();
  expect(f.dispatches).toBe(1);
  expect(f.payments).toBe(0);
  f.assertClean();
});
