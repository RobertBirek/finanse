import { expect, type Page } from "@playwright/test";
import { account, fixtures } from "./fixtures";

export const loanId = "71000000-0000-0000-0000-000000000001";
export const installmentId = "72000000-0000-0000-0000-000000000001";
const debtId = "73000000-0000-0000-0000-000000000001";
const candidates = [
  {
    transaction_id: "74000000-0000-0000-0000-000000000001",
    transaction_date: "2026-10-15",
    description: "Pierwsza część raty",
    amount_pln: 40000,
  },
  {
    transaction_id: "74000000-0000-0000-0000-000000000002",
    transaction_date: "2026-10-16",
    description: "Druga część raty",
    amount_pln: 60000,
  },
];

/** Synthetic loan metadata only. Base fixtures reject any real ledger write. */
export async function loanFixtures(
  page: Page,
  options: {
    listError?: boolean;
    conflict?: boolean;
    emptySchedule?: boolean;
    paginated?: boolean;
    pauseLink?: boolean;
    unlinkConflict?: boolean;
  } = {},
) {
  const api = await fixtures(page);
  let nextLink = 1;
  let hasInstallment = !options.emptySchedule;
  let releaseLink = () => {};
  const linkGate = options.pauseLink
    ? new Promise<void>((resolve) => {
        releaseLink = resolve;
      })
    : Promise.resolve();
  const availableCandidates = options.paginated
    ? [
        ...candidates,
        ...Array.from({ length: 19 }, (_, index) => ({
          transaction_id: `74000000-0000-0000-0000-${String(index + 3).padStart(12, "0")}`,
          transaction_date: "2026-10-16",
          description: `Dodatkowa płatność ${index + 3}`,
          amount_pln: 40000,
        })),
      ]
    : candidates;
  const payments: Array<{
    id: string;
    transaction_id: string;
    transaction_date: string;
    amount_pln: number;
  }> = [];
  const mutations: Array<{ method: string; path: string; body: unknown }> = [];
  const unknown: string[] = [];
  const detail = () => {
    const paid = payments.reduce((sum, p) => sum + p.amount_pln, 0);
    return {
      id: loanId,
      name: "Kredyt testowy Q7",
      account_id: debtId,
      payment_account_id: account.id,
      is_active: true,
      currency: "PLN",
      ledger_balance_pln: -300000,
      planned_principal_pln: hasInstallment ? 90000 : 0,
      planned_interest_pln: hasInstallment ? 9000 : 0,
      planned_fees_pln: hasInstallment ? 1000 : 0,
      total_planned_pln: hasInstallment ? 100000 : 0,
      paid_pln: paid,
      remaining_pln: (hasInstallment ? 100000 : 0) - paid,
      requires_accounting_review: true,
      installments: hasInstallment
        ? [
            {
              id: installmentId,
              number: 1,
              due_date: "2026-10-15",
              principal_pln: 90000,
              interest_pln: 9000,
              fees_pln: 1000,
              total_pln: 100000,
              paid_pln: paid,
              remaining_pln: 100000 - paid,
              payment_status:
                paid === 100000 ? "paid" : paid ? "partial" : "unpaid",
              payments,
            },
          ]
        : [],
    };
  };
  await page.route("**/api/finance/accounts", (route) =>
    route.fulfill({
      json: [
        {
          ...account,
          name: "Rachunek spłaty",
          currency: "PLN",
          balance_source: 500000,
          balance_pln: 500000,
        },
        {
          ...account,
          id: debtId,
          name: "Konto zadłużenia",
          currency: "PLN",
          is_budget_account: false,
          balance_source: -300000,
          balance_pln: -300000,
        },
      ],
    }),
  );
  await page.route("**/api/finance/loans**", async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname;
    const method = request.method();
    if (method !== "GET")
      mutations.push({ method, path, body: request.postDataJSON() });
    if (path === "/api/finance/loans" && method === "GET") {
      return route.fulfill(
        options.listError
          ? { status: 503, json: { detail: "Fixture unavailable" } }
          : { json: [detail()] },
      );
    }
    if (path === `/api/finance/loans/${loanId}` && method === "GET")
      return route.fulfill({ json: detail() });
    if (
      path === `/api/finance/loans/${loanId}/installments` &&
      method === "POST" &&
      !hasInstallment
    ) {
      expect(request.postDataJSON()).toEqual({
        number: 1,
        due_date: "2026-10-15",
        principal_pln: 90000,
        interest_pln: 9000,
        fees_pln: 1000,
      });
      hasInstallment = true;
      return route.fulfill({ status: 201, json: detail().installments[0] });
    }
    if (path.endsWith("/payment-candidates") && method === "GET") {
      const available = availableCandidates.filter(
        (c) =>
          !payments.some((p) => p.transaction_id === c.transaction_id) &&
          c.amount_pln <= detail().remaining_pln,
      );
      const offset = Number(url.searchParams.get("offset") ?? 0),
        limit = Number(url.searchParams.get("limit") ?? 25);
      return route.fulfill({
        json: {
          items: available.slice(offset, offset + limit),
          total: available.length,
          offset,
          limit,
        },
      });
    }
    if (
      path ===
        `/api/finance/loans/${loanId}/installments/${installmentId}/payments` &&
      method === "POST"
    ) {
      await linkGate;
      if (options.conflict)
        return route.fulfill({
          status: 409,
          json: { detail: "Płatność jest już powiązana." },
        });
      const body = request.postDataJSON() as { transaction_id: string };
      const found = availableCandidates.find(
        (c) => c.transaction_id === body.transaction_id,
      );
      expect(found).toBeDefined();
      if (
        found &&
        !payments.some((p) => p.transaction_id === found.transaction_id)
      )
        payments.push({
          id: `75000000-0000-0000-0000-${String(nextLink++).padStart(12, "0")}`,
          ...found,
        });
      return route.fulfill({ json: detail() });
    }
    const unlink = path.match(/\/payments\/([a-f0-9-]+)$/);
    if (unlink && method === "DELETE") {
      if (options.unlinkConflict)
        return route.fulfill({
          status: 409,
          json: { detail: "Nie udało się odpiąć płatności." },
        });
      const index = payments.findIndex((p) => p.id === unlink[1]);
      expect(index).toBeGreaterThanOrEqual(0);
      if (index >= 0) payments.splice(index, 1);
      return route.fulfill({ status: 204 });
    }
    unknown.push(method + " " + path);
    return route.fulfill({
      status: 422,
      json: { detail: "Unregistered loan fixture operation" },
    });
  });
  return {
    ...api,
    loanMutations: mutations,
    releaseLink: () => releaseLink(),
    assertLoanClean: () => {
      api.assertClean();
      expect(unknown).toEqual([]);
      expect(api.mutations).toEqual([]);
    },
  };
}
