import {
  batchFixture,
  httpFailure,
  installImportServer,
  rowFixture,
  source,
  type ImportRequest,
} from "./bankImportFixtures";

export const scheduleRow = {
  bank_number: 1,
  due_date: "2026-12-15",
  principal: 100000,
  interest: 2000,
  fees: 0,
  total: 102000,
  balance_after: 0,
  position: { page: 1, line: 10, section: "loan_schedule" },
};
export const scheduleLoan = {
  id: "loan-a",
  name: "Umowa syntetyczna",
  account_id: "debt-a",
  payment_account_id: "payer-a",
  is_active: true,
  currency: "PLN" as const,
  ledger_balance_pln: -100000,
  planned_principal_pln: 100000,
  planned_interest_pln: 2000,
  planned_fees_pln: 0,
  total_planned_pln: 102000,
  paid_pln: 100,
  remaining_pln: 101900,
  requires_accounting_review: true,
};
export const scheduleInstallment = {
  id: "installment-a",
  number: 45,
  bank_number: 1,
  schedule_revision_id: "bank-version",
  due_date: scheduleRow.due_date,
  principal_pln: 100000,
  interest_pln: 2000,
  fees_pln: 0,
  total_pln: 102000,
  paid_pln: 100,
  remaining_pln: 101900,
  payment_status: "partial" as const,
  payments: [],
};
export const schedulePreview = {
  id: "schedule-preview",
  batch_id: "batch-a",
  version: 2,
  request_hash: "c".repeat(64),
  source_revision_id: "revision-a",
  target: { loan_id: "loan-a", new_loan: null },
  cutover_date: "2026-11-11",
  loan_fingerprint: "d".repeat(64),
  diff: {
    cutover_date: "2026-11-11",
    reused_ids: ["installment-a"],
    new_rows: [],
    superseded_ids: ["old-future"],
    retained_history_ids: ["past-unpaid"],
    conflicts: [],
    warnings: ["retained_history"],
    fingerprint: "d".repeat(64),
  },
  ledger_effect: "none" as const,
};
export const scheduleReceipt = {
  receipt_id: "schedule-receipt",
  batch_id: "batch-a",
  request_hash: schedulePreview.request_hash,
  loan_id: "loan-a",
  revision_id: "bank-version",
  reused_ids: ["installment-a"],
  new_ids: [],
  superseded_ids: ["old-future"],
  ledger_changed: false as const,
};
export function scheduleBatch() {
  return batchFixture({
    kind: "loan_schedule",
    groups: [],
    sources: [
      {
        ...source,
        checks: source.checks.map((check) => ({ ...check })),
        warnings: [...source.warnings],
        original_name: "schedule.pdf",
        layout: "velo_remaining_schedule_pln_v1",
      },
    ],
    unresolved_count: 1,
  });
}
export const historyVersions = [
  {
    id: "bank-version",
    loan_id: "loan-a",
    ordinal: 2,
    kind: "bank_import",
    state: "active",
    previous_revision_id: "manual-version",
    source_revision_id: "revision-a",
    receipt_id: "schedule-receipt",
    bank_effective_date: "2026-11-01",
    activated_on: "2026-11-11",
    cutover_date: "2026-11-11",
    document_id: "document-a",
    original_name: "schedule.pdf",
    batch_id: "batch-a",
  },
  {
    id: "manual-version",
    loan_id: "loan-a",
    ordinal: 1,
    kind: "manual_baseline",
    state: "superseded",
    previous_revision_id: null,
    source_revision_id: null,
    receipt_id: "schedule-receipt",
    bank_effective_date: null,
    activated_on: "2026-11-11",
    cutover_date: "2026-11-11",
    document_id: null,
    original_name: null,
    batch_id: null,
  },
];
export function installScheduleServer(
  options: {
    onRequest?: (request: ImportRequest) => Promise<unknown> | unknown;
    conflict?: boolean;
  } = {},
) {
  let batch = scheduleBatch();
  const preview = {
    ...schedulePreview,
    diff: options.conflict
      ? {
          ...schedulePreview.diff,
          conflicts: [
            {
              code: "linked_future_missing_or_changed",
              row_key: "1",
              installment_ids: ["installment-a"],
            },
          ],
        }
      : schedulePreview.diff,
  };
  return installImportServer({
    batch,
    rows: [
      rowFixture({
        kind: "loan_schedule",
        bank_fields: null,
        schedule_fields: scheduleRow,
        decision: null,
      }),
    ],
    onRequest: async (request) => {
      const custom = await options.onRequest?.(request);
      if (custom !== undefined) return custom;
      const { url, method } = request;
      if (url === "/finance/loans") return [scheduleLoan];
      if (url === "/finance/loans/loan-a")
        return {
          ...scheduleLoan,
          active_schedule_revision_id: "bank-version",
          installments: [scheduleInstallment],
        };
      if (url === "/finance/accounts")
        return [
          {
            id: "debt-a",
            name: "Konto długu",
            type: "credit",
            currency: "PLN",
            is_active: true,
          },
          {
            id: "payer-a",
            name: "Konto spłaty",
            type: "checking",
            currency: "PLN",
            is_active: true,
          },
          {
            id: "inactive",
            name: "Nieaktywne",
            type: "checking",
            currency: "PLN",
            is_active: false,
          },
          {
            id: "card",
            name: "Karta",
            type: "credit_card",
            currency: "PLN",
            is_active: true,
          },
        ];
      if (url === "/finance/imports" && method === "post")
        return { ...batch, sources: [] };
      if (url.endsWith("/sources"))
        return {
          source: batch.sources[0],
          is_duplicate: false,
          existing_batch_id: null,
        };
      if (url.endsWith("/schedule-preview")) return preview;
      if (url.endsWith("/activate-schedule")) {
        batch = { ...batch, version: 3, commit_state: "committed" };
        return scheduleReceipt;
      }
      if (url.includes("/commands/")) return scheduleReceipt;
      if (url.endsWith("/schedule-revisions")) return historyVersions;
      if (url.includes("/schedule-revisions/")) {
        const version = historyVersions.find((v) => url.endsWith(v.id));
        if (!version) throw httpFailure(404, {}, request.config);
        return {
          ...version,
          installments: [
            {
              installment_id: "installment-a",
              bank_number: version.kind === "bank_import" ? 1 : null,
              source_row_id: version.kind === "bank_import" ? "row-a" : null,
              due_date: scheduleRow.due_date,
              principal_pln: 100000,
              interest_pln: 2000,
              fees_pln: 0,
              balance_after_pln: 0,
            },
          ],
        };
      }
      if (url === "/finance/imports/batch-a") return batch;
      return undefined;
    },
  });
}
