import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders, type AxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import type {
  ImportBatch,
  ImportRow,
  ImportPreview,
  CommitResult,
} from "../api/bankImports";

export const source = {
  id: "source-a",
  batch_id: "batch-a",
  document_id: "document-a",
  sha256: "a".repeat(64),
  original_name: "statement.pdf",
  bank: "velo",
  layout: "velo_account",
  parser_version: "v1",
  processing_state: "ready",
  validation_state: "passed",
  current_revision_id: "revision-a",
  candidate_revision_id: null,
  candidate_parser_version: null,
  checks: [
    {
      code: "balance_rollforward",
      required: true,
      result: "passed",
      expected: 900,
      actual: 900,
    },
  ],
  warnings: [],
} as const;

export function batchFixture(changes: Partial<ImportBatch> = {}): ImportBatch {
  return {
    id: "batch-a",
    kind: "statement",
    version: 2,
    archived_at: null,
    commit_state: "not_committed",
    unresolved_count: 1,
    sources: [JSON.parse(JSON.stringify(source))],
    groups: [
      {
        id: "group-a",
        version: 1,
        state: "ready",
        row_ids: ["row-a"],
        decision: {
          group_id: "group-a",
          row_ids: ["row-a"],
          action: "create",
          kind: "expense",
          account_id: "account-pln",
          category_id: "category-a",
          acknowledgements: [],
        },
      },
    ],
    ...changes,
  };
}
export function rowFixture(changes: Partial<ImportRow> = {}): ImportRow {
  return {
    id: "row-a",
    source_id: "source-a",
    revision_id: "revision-a",
    source_key: "p1l4",
    kind: "statement",
    position: { page: 1, line: 4, section: null },
    bank_fields: {
      key: "p1l4",
      position: { page: 1, line: 4, section: null },
      booking_date: "2026-01-03",
      operation_date: "2026-01-02",
      started_at: null,
      completed_at: null,
      description: "Syntetyczny zakup",
      amount: -100,
      fee: 0,
      currency: "PLN",
      state: "posted",
      balance_after: 900,
      bank_reference: null,
      raw: {},
    },
    schedule_fields: null,
    candidate_ids: [],
    decision: batchFixture().groups[0].decision,
    ...changes,
  };
}
export function previewFixture(): ImportPreview {
  return {
    id: "preview-a",
    batch_id: "batch-a",
    version: 2,
    request_hash: "b".repeat(64),
    new_transaction_count: 1,
    linked_count: 0,
    unresolved_count: 1,
    warnings: [],
    quotes: [
      {
        currency: "PLN",
        requested_date: "2026-01-03",
        effective_date: "2026-01-03",
        rate: "1",
        source: "pln",
        base_amount: 100,
      },
    ],
    groups: [
      {
        group_id: "group-a",
        action: "create",
        operations: [
          {
            kind: "expense",
            component: "main",
            row_ids: ["row-a"],
            booking_date: "2026-01-03",
            purchase_date: "2026-01-02",
            description: "Syntetyczny zakup",
            quote: {
              currency: "PLN",
              requested_date: "2026-01-03",
              effective_date: "2026-01-03",
              rate: "1",
              source: "pln",
              base_amount: 100,
            },
            postings: [
              {
                account_id: "account-pln",
                category_id: null,
                source_amount: 100,
                source_currency: "PLN",
                base_amount_pln: 100,
                fx_rate: "1",
                fx_rate_source: "pln",
                direction: "debit",
              },
              {
                account_id: null,
                category_id: "category-a",
                source_amount: 100,
                source_currency: "PLN",
                base_amount_pln: 100,
                fx_rate: "1",
                fx_rate_source: "pln",
                direction: "credit",
              },
            ],
          },
        ],
      },
    ],
  };
}
export const receiptFixture: CommitResult = {
  receipt_id: "receipt-a",
  batch_id: "batch-a",
  request_hash: "b".repeat(64),
  transaction_ids: ["txn-a"],
  linked_row_ids: [],
  remaining_group_ids: [],
  commit_state: "committed",
};

export function setImportActor(id = "owner-a") {
  useAuthStore.setState({
    user: {
      id,
      email: `${id}@example.test`,
      display_name: "Synthetic",
      is_active: true,
    },
    authStatus: "loading",
    sessionVersion: useAuthStore.getState().sessionVersion + 1,
  });
}

export interface ImportRequest {
  method: string;
  url: string;
  body: unknown;
  key: string | null;
  config: AxiosRequestConfig;
}
export function installImportServer(
  options: {
    batch?: ImportBatch;
    rows?: ImportRow[];
    onRequest?: (request: ImportRequest) => Promise<unknown> | unknown;
  } = {},
) {
  setImportActor();
  const original = api.defaults.adapter;
  const requests: ImportRequest[] = [];
  let batch = options.batch ?? batchFixture();
  let recovered: CommitResult | null = null;
  api.defaults.adapter = async (config) => {
    const request: ImportRequest = {
      method: config.method ?? "get",
      url: config.url ?? "",
      body:
        typeof config.data === "string" ? JSON.parse(config.data) : config.data,
      key: config.headers.get("Idempotency-Key") as string | null,
      config,
    };
    requests.push(request);
    const custom = await options.onRequest?.(request);
    const respond = (data: unknown) => ({
      data: JSON.parse(JSON.stringify(data)),
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
    });
    if (custom !== undefined) return respond(custom);
    const path = request.url;
    if (path === "/finance/imports" && request.method === "get")
      return respond([batch]);
    if (path === "/finance/imports" && request.method === "post") {
      batch = batchFixture({
        version: 1,
        sources: [],
        groups: [],
        unresolved_count: 0,
      });
      return respond(batch);
    }
    if (path === "/finance/accounts")
      return respond(
        ["PLN", "EUR", "USD"].map((currency) => ({
          id: `account-${currency.toLowerCase()}`,
          name: `Rachunek ${currency}`,
          currency,
          type: "checking",
          is_active: true,
        })),
      );
    if (path === "/finance/categories")
      return respond([
        {
          id: "category-a",
          name: "Zakupy",
          type: "expense",
          is_active: true,
          parent_id: null,
        },
      ]);
    if (path.endsWith("/rows"))
      return respond({
        items: options.rows ?? [rowFixture()],
        total: (options.rows ?? [rowFixture()]).length,
        offset: 0,
        limit: 100,
      });
    if (path.endsWith("/candidates")) return respond([]);
    if (path.endsWith("/sources")) {
      batch = batchFixture();
      return respond({ source, is_duplicate: false, existing_batch_id: null });
    }
    if (path.endsWith("/prepare"))
      return respond({
        id: "job-a",
        state: "ready",
        source_id: source.id,
        revision_id: "revision-a",
        attempt: 1,
        error_code: null,
      });
    if (path.endsWith("/decisions")) {
      const body = request.body as {
        decisions: ImportBatch["groups"][number]["decision"][];
      };
      batch = {
        ...batch,
        version: batch.version + 1,
        groups: body.decisions.map((decision) => ({
          id: decision!.group_id,
          version: 1,
          state: decision!.action === "defer" ? "deferred" : "ready",
          row_ids: decision!.row_ids,
          decision,
        })),
      };
      return respond(batch);
    }
    if (path.endsWith("/preview")) return respond(previewFixture());
    if (path.endsWith("/commit")) {
      recovered = receiptFixture;
      return respond(recovered);
    }
    if (path.includes("/commands/")) {
      if (recovered) return respond(recovered);
      throw httpFailure(404, { code: "command_not_found" }, config);
    }
    if (/^\/finance\/imports\/[^/]+$/.test(path)) return respond(batch);
    throw new Error(
      `Unexpected import fixture request: ${request.method} ${path}`,
    );
  };
  return {
    requests,
    setReceipt: (value: CommitResult) => {
      recovered = value;
    },
    setBatch: (value: ImportBatch) => {
      batch = value;
    },
    restore: () => {
      api.defaults.adapter = original;
    },
  };
}
export function httpFailure(
  status: number,
  data: unknown,
  config?: AxiosRequestConfig,
): AxiosError {
  return new AxiosError(
    "Synthetic HTTP error",
    "ERR_BAD_REQUEST",
    undefined,
    undefined,
    {
      data,
      status,
      statusText: "Error",
      headers: new AxiosHeaders(),
      config: { ...config, headers: new AxiosHeaders() },
    },
  );
}
export function importTestWrapper(
  children: ReactNode,
  path = "/finances/imports",
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    node: (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </QueryClientProvider>
    ),
  };
}
