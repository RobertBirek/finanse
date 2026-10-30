import { expect, type Page } from "@playwright/test";
import { fixtures } from "./fixtures";

export const ids = {
  oldPdf: "d1000000-0000-0000-0000-000000000001",
  heic: "d1000000-0000-0000-0000-000000000002",
  receipt: "d1000000-0000-0000-0000-000000000003",
  bill: "b1000000-0000-0000-0000-000000000001",
  posting40: "p1000000-0000-0000-0000-000000000040",
  posting60: "p1000000-0000-0000-0000-000000000060",
  schedule: "s1000000-0000-0000-0000-000000000001",
};

/** Stateful synthetic API: it records real UI contracts and never accepts an unregistered write. */
export async function financialDocumentFixtures(
  page: Page,
  options: { reviewError?: boolean; invoiceTotalMinor?: number } = {},
) {
  const base = await fixtures(page);
  const mutations: Array<{
    method: string;
    path: string;
    body: unknown;
    key: string | null;
  }> = [];
  const unknown: string[] = [];
  let version = 2,
    paid = 0,
    attached = false,
    covered = false,
    heifUploaded = false,
    receiptApproved = false;
  const invoiceTotalMinor = options.invoiceTotalMinor ?? 10000;
  const bill = () => ({
    id: ids.bill,
    kind: "invoice",
    supplier_name: "Stary dostawca",
    supplier_tax_id: null,
    number: "FV-100",
    issue_date: "2026-10-20",
    sale_date: null,
    due_date: "2026-11-09",
    payee_iban: null,
    description: "Usługa testowa",
    category_id: "c1",
    payment_account_id: "a1",
    total_minor: invoiceTotalMinor,
    currency: "PLN",
    declaration: "payable",
    lifecycle: "active",
    review: "approved",
    version,
    paid_minor: paid,
    remaining_minor: invoiceTotalMinor - paid,
    reconciliation:
      paid === invoiceTotalMinor ? "full" : paid ? "partial" : "none",
    sources: [
      { document_id: ids.oldPdf },
      ...(attached ? [{ document_id: ids.heic }] : []),
    ],
    allocations: paid
      ? [
          {
            id: `allocation-${paid}`,
            posting_id: paid === 4000 ? ids.posting40 : ids.posting60,
            amount_minor: paid === 4000 ? 4000 : 6000,
          },
        ]
      : [],
    extraction_revision_id: null,
    coverage: covered
      ? {
          scheduled_item_id: ids.schedule,
          occurrence_date: "2026-11-05",
          choice: "replace",
          source_lifecycle: "active",
        }
      : null,
    recurring_decision: null,
    forecast_exclusion_reasons: [],
  });
  const docs = [
    {
      id: ids.oldPdf,
      original_name: "stara-faktura.pdf",
      status: "done",
      mime_type: "application/pdf",
      size_bytes: 100,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
      user_id: "qa",
      filename: "old.pdf",
      sha256_hash: "a".repeat(64),
      attempt_count: 0,
      next_attempt_at: null,
      last_error_code: null,
    },
    {
      id: ids.receipt,
      original_name: "paragon.pdf",
      status: "error",
      mime_type: "application/pdf",
      size_bytes: 100,
      created_at: "2026-10-20T10:02:00Z",
      updated_at: "2026-10-20T10:02:00Z",
      user_id: "qa",
      filename: "receipt.pdf",
      sha256_hash: "c".repeat(64),
      attempt_count: 1,
      next_attempt_at: null,
      last_error_code: "ocr_failed",
    },
  ];
  const forecast = () => ({
    last_payday: "2026-10-10",
    next_payday: "2026-11-10",
    opening_balance_pln: 50_000,
    projected_balance_before_next_payday_pln: 38_000,
    lowest_balance_pln: 38_000,
    safe_daily_limit_pln: 1_000,
    days: [],
    budgets: { total_budget_pln: 0, total_spent_pln: 0, remaining_pln: 0 },
    suggestions: [
      ...(covered
        ? []
        : [
            {
              name: "Abonament — listopad",
              type: "expense",
              due_date: "2026-11-05",
              amount_pln: 10000,
              status: "due",
              included_in_forecast: true,
              actual_transaction_id: null,
              source_key: "recurring-november",
              exclusion_reasons: [],
              source: "recurring",
              scheduled_item_id: ids.schedule,
              financial_document_id: null,
            },
          ]),
      {
        name: `Faktura ${invoiceTotalMinor / 100} — listopad`,
        type: "expense",
        due_date: "2026-11-05",
        amount_pln: invoiceTotalMinor,
        status: "due",
        included_in_forecast: true,
        actual_transaction_id: null,
        source_key: "financial-document-november",
        exclusion_reasons: [],
        source: "financial_document",
        scheduled_item_id: null,
        financial_document_id: ids.bill,
      },
      {
        name: "Abonament — grudzień",
        type: "expense",
        due_date: "2026-12-05",
        amount_pln: 10000,
        status: "due",
        included_in_forecast: true,
        actual_transaction_id: null,
        source_key: "recurring-december",
        exclusion_reasons: [],
        source: "recurring",
        scheduled_item_id: ids.schedule,
        financial_document_id: null,
      },
    ],
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname,
      method = req.method();
    if (path === "/api/documents" && method === "GET")
      return route.fulfill({ json: docs });
    if (path === "/api/documents/upload" && method === "POST") {
      mutations.push({ method, path, body: "synthetic-heif", key: null });
      expect(req.postDataBuffer().includes(Buffer.from("ftypheic"))).toBe(true);
      heifUploaded = true;
      const document = {
        id: ids.heic,
        original_name: "ten-sam-zakup.heif",
        status: "done",
        mime_type: "image/heif",
        size_bytes: 24,
        created_at: "2026-10-20T10:01:00Z",
        updated_at: "2026-10-20T10:01:00Z",
        user_id: "qa",
        filename: "same.heif",
        sha256_hash: "b".repeat(64),
        attempt_count: 0,
        next_attempt_at: null,
        last_error_code: null,
      };
      docs.push(document);
      return route.fulfill({
        status: 201,
        json: { document, is_duplicate: false },
      });
    }
    if (path === "/api/documents/upload-capabilities" && method === "GET")
      return route.fulfill({
        json: {
          max_file_bytes: 20 * 1024 * 1024,
          accepted_mime_types: [
            "application/pdf",
            "image/heic",
            "image/heif",
            "image/jpeg",
            "image/png",
          ],
        },
      });
    if (
      [ids.oldPdf, ids.heic].includes(path.split("/")[3]) &&
      path.endsWith("/text")
    )
      return route.fulfill({
        json: {
          id: "t",
          document_id: path.split("/")[3],
          extracted_text: "Synthetic document",
          ocr_engine: "test",
          extracted_at: null,
          created_at: "2026-10-20T10:00:00Z",
        },
      });
    if (
      [ids.oldPdf, ids.heic].includes(path.split("/")[3]) &&
      path.endsWith("/review")
    )
      return route.fulfill({
        json: {
          id: "r",
          document_id: path.split("/")[3],
          revision: 1,
          status: options.reviewError ? "error" : "ready",
          error_code: options.reviewError ? "llm_failed" : null,
          document_type: "invoice",
          fields: {
            supplier_name: "Stary dostawca",
            supplier_tax_id: null,
            number: "FV-100",
            issue_date: "2026-10-20",
            sale_date: null,
            due_date: "2026-11-09",
            description: "Usługa testowa",
            payee_iban: null,
            total: "100.00",
            currency: "PLN",
          },
          provenance: {},
          parser_version: "test",
        },
      });
    if (path === `/api/documents/${ids.receipt}/review`)
      return route.fulfill({
        json: {
          id: "receipt-review",
          document_id: ids.receipt,
          revision: 1,
          status: "ready",
          error_code: null,
          document_type: "receipt",
          fields: {
            supplier_name: "Receipt shop",
            supplier_tax_id: null,
            number: null,
            issue_date: "2026-10-20",
            sale_date: null,
            due_date: null,
            description: "Paid receipt",
            payee_iban: null,
            total: "10.00",
            currency: "PLN",
          },
          provenance: {},
          parser_version: "test",
        },
      });
    if (path.includes("/preview") || path.includes("/original"))
      return route.fulfill({ status: 404 });
    if (path === "/api/finance/accounts")
      return route.fulfill({
        json: [
          {
            id: "a1",
            name: "Konto testowe",
            type: "checking",
            currency: "PLN",
            is_active: true,
            is_budget_account: true,
            balance_pln: 0,
          },
        ],
      });
    if (path === "/api/finance/categories")
      return route.fulfill({
        json: [{ id: "c1", name: "Usługi", type: "expense", is_active: true }],
      });
    if (path === "/api/finance/cashflow/forecast" && method === "GET")
      return route.fulfill({ json: forecast() });
    if (path === "/api/finance/bills" && method === "GET")
      return route.fulfill({
        json: { items: [bill()], total: 1, limit: 25, offset: 0 },
      });
    if (path === `/api/finance/bills/${ids.bill}` && method === "GET")
      return route.fulfill({ json: bill() });
    if (path === "/api/finance/bills/receipt-bill" && method === "GET")
      return route.fulfill({
        json: {
          ...bill(),
          id: "receipt-bill",
          kind: "receipt",
          supplier_name: "Receipt shop",
          total_minor: 1000,
          remaining_minor: 1000,
          paid_minor: 0,
          declaration: "declared_paid",
          reconciliation: "none",
          version: 2,
          sources: [{ document_id: ids.receipt }],
          allocations: [],
        },
      });
    if (
      path === `/api/finance/bills/${ids.bill}/duplicates` &&
      method === "GET"
    )
      return route.fulfill({ json: [] });
    if (path === "/api/finance/bills/heif-draft/duplicates" && method === "GET")
      return route.fulfill({
        json: [{ id: ids.bill, reasons: ["same_purchase"] }],
      });
    if (
      path === "/api/finance/bills/receipt-draft/duplicates" &&
      method === "GET"
    )
      return route.fulfill({ json: [] });
    if (
      path === `/api/finance/bills/${ids.bill}/candidates` &&
      method === "GET"
    )
      return route.fulfill({
        json: {
          items: paid
            ? [
                {
                  transaction_id: "t60",
                  posting_id: ids.posting60,
                  date: "2026-10-21",
                  account: "Konto testowe",
                  amount_minor: 6000,
                  unallocated_minor: 6000,
                  reasons: [],
                  legacy_inbox_reference: null,
                  recurring_conflicts: [],
                  recurring_forecast_before_pln: null,
                  recurring_forecast_after_pln: null,
                },
              ]
            : [
                {
                  transaction_id: "t40",
                  posting_id: ids.posting40,
                  date: "2026-10-20",
                  account: "Konto testowe",
                  amount_minor: 4000,
                  unallocated_minor: 4000,
                  reasons: [],
                  legacy_inbox_reference: null,
                  recurring_conflicts: [],
                  recurring_forecast_before_pln: null,
                  recurring_forecast_after_pln: null,
                },
              ],
          total: 1,
          limit: 20,
          offset: 0,
        },
      });
    if (
      path === `/api/finance/bills/${ids.bill}/coverage-candidates` &&
      method === "GET"
    )
      return route.fulfill({
        json: [
          {
            scheduled_item_id: ids.schedule,
            occurrence_date: "2026-11-05",
            name: "Abonament",
            estimate_amount_pln: 10000,
          },
        ],
      });
    if (method !== "GET")
      mutations.push({
        method,
        path,
        body: req.postDataJSON(),
        key: req.headerValue("Idempotency-Key"),
      });
    if (
      path === `/api/finance/bills/${ids.bill}/allocations` &&
      method === "POST"
    ) {
      const body = req.postDataJSON() as {
        version: number;
        amount_minor: number;
      };
      expect(body.version).toBe(version);
      paid += body.amount_minor;
      version++;
      return route.fulfill({ json: bill() });
    }
    if (
      path === `/api/finance/bills/${ids.bill}/coverage` &&
      method === "POST"
    ) {
      const body = req.postDataJSON() as { version: number; choice: string };
      expect(body.version).toBe(version);
      expect(body.choice).toBe("replace");
      covered = true;
      version++;
      return route.fulfill({ json: bill() });
    }
    if (
      path === `/api/finance/bills/${ids.bill}/sources/${ids.heic}` &&
      method === "POST"
    ) {
      attached = true;
      version++;
      return route.fulfill({ json: bill() });
    }
    if (
      path === `/api/finance/bills/prepare/${ids.oldPdf}` &&
      method === "POST"
    )
      return route.fulfill({
        status: 201,
        json: { ...bill(), review: "draft", version: 1 },
      });
    if (
      path === `/api/finance/bills/prepare/${ids.heic}` &&
      method === "POST"
    ) {
      expect(heifUploaded).toBe(true);
      return route.fulfill({
        status: 201,
        json: { ...bill(), id: "heif-draft", review: "draft", version: 1 },
      });
    }
    if (
      path === `/api/finance/bills/prepare/${ids.receipt}` &&
      method === "POST"
    )
      return route.fulfill({
        status: 201,
        json: { ...bill(), id: "receipt-draft", review: "draft", version: 1 },
      });
    if (path === `/api/finance/bills/${ids.bill}/approve` && method === "POST")
      return route.fulfill({ json: bill() });
    if (
      path === "/api/finance/bills/receipt-draft/approve" &&
      method === "POST"
    ) {
      receiptApproved = true;
      expect((req.postDataJSON() as { declaration: string }).declaration).toBe(
        "declared_paid",
      );
      return route.fulfill({
        json: {
          ...bill(),
          id: "receipt-bill",
          kind: "receipt",
          supplier_name: "Receipt shop",
          total_minor: 1000,
          remaining_minor: 1000,
          paid_minor: 0,
          declaration: "declared_paid",
          reconciliation: "none",
          version: 2,
          sources: [{ document_id: ids.receipt }],
          allocations: [],
        },
      });
    }
    if (path === `/api/documents/${ids.oldPdf}/retry-ocr` && method === "POST")
      return route.fulfill({ status: 202, json: {} });
    await route.fallback();
  });
  return {
    mutations,
    isReceiptApproved: () => receiptApproved,
    assertClean: () => {
      base.assertClean();
      expect(unknown).toEqual([]);
      expect(
        mutations
          .filter((m) => m.path.startsWith("/api/finance/bills/"))
          .every((m) => !!m.key),
      ).toBe(true);
    },
  };
}
