import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import {
  captureProcessingActor,
  isProcessingActorCurrent,
  useDocumentProcessingStore,
  type ProcessingActor,
} from "../stores/documentProcessingStore";
import {
  invalidateFinanceLedger,
  type Account,
  type Category,
  type Transaction,
} from "./finance";

export type ImportCurrency = "PLN" | "EUR" | "USD";
export type ImportKind = "statement" | "loan_schedule";
export type ImportTransactionKind =
  "expense" | "income" | "expense_refund" | "transfer" | "exchange";
export interface SourcePosition {
  page: number | null;
  line: number;
  section: string | null;
}
export interface ImportCheck {
  code: string;
  required: boolean;
  result: "passed" | "failed" | "unavailable";
  expected: number | null;
  actual: number | null;
}
export interface ImportSource {
  id: string;
  batch_id: string;
  document_id: string;
  sha256: string;
  original_name: string;
  bank: "velo" | "ing" | "revolut" | null;
  layout: string | null;
  parser_version: string | null;
  processing_state: "queued" | "processing" | "ready" | "error" | "unsupported";
  validation_state: "passed" | "needs_review" | "blocked";
  current_revision_id: string | null;
  candidate_revision_id?: string | null;
  candidate_parser_version?: string | null;
  checks: ImportCheck[];
  warnings: string[];
}
export interface BankStatementRow {
  key: string;
  position: SourcePosition;
  booking_date: string | null;
  operation_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  description: string;
  amount: number;
  fee: number;
  currency: ImportCurrency;
  state: "posted" | "pending" | "reverted" | "cancelled" | "unknown";
  balance_after: number | null;
  bank_reference: string | null;
  raw: Record<string, unknown>;
}
export interface CardHeaderDecision {
  account_id: string;
  period_start: string;
  period_end: string;
  due_date: string;
  debt_pln: number;
  minimum_pln: number;
  debt_definition_confirmed: boolean;
}
export interface ImportDecision {
  group_id: string;
  row_ids: string[];
  action: "create" | "link" | "defer";
  kind?: ImportTransactionKind | null;
  account_id?: string | null;
  other_account_id?: string | null;
  category_id?: string | null;
  existing_transaction_id?: string | null;
  fee_category_id?: string | null;
  manual_rate?: string | null;
  acknowledgements: string[];
  card_header?: CardHeaderDecision | null;
}
export interface ImportGroup {
  id: string;
  version: number;
  state: "draft" | "ready" | "committed" | "deferred";
  row_ids: string[];
  decision: ImportDecision | null;
}
export interface ImportBatch {
  id: string;
  kind: ImportKind;
  version: number;
  archived_at: string | null;
  commit_state: "not_committed" | "partial" | "committed";
  sources: ImportSource[];
  unresolved_count: number;
  groups: ImportGroup[];
}
export interface ImportRow {
  id: string;
  source_id: string;
  revision_id: string;
  source_key: string;
  position: SourcePosition;
  kind: ImportKind;
  bank_fields: BankStatementRow | null;
  schedule_fields: Record<string, unknown> | null;
  candidate_ids: string[];
  decision: ImportDecision | null;
}
export interface ImportRowPage {
  items: ImportRow[];
  total: number;
  offset: number;
  limit: number;
}
export interface ImportUploadResult {
  source: ImportSource;
  is_duplicate: boolean;
  existing_batch_id: string | null;
}
export interface ImportJob {
  id: string;
  source_id: string;
  revision_id: string;
  state: ImportSource["processing_state"];
  attempt: number;
  error_code: string | null;
}
export interface ExistingCandidate {
  transaction_id: string;
  account_posting_id: string;
  strength: "strong" | "possible";
  reasons: string[];
  conflicts: string[];
}
export interface FrozenQuote {
  currency?: ImportCurrency;
  requested_date?: string;
  effective_date?: string;
  rate?: string;
  source?: string;
  base_amount?: number;
  base_pln?: number;
  from_rate?: string;
  to_rate?: string;
  from_source?: string;
  to_source?: string;
  quote_date?: string;
}
export interface FrozenPosting {
  account_id: string | null;
  category_id: string | null;
  source_amount: number;
  source_currency: ImportCurrency;
  base_amount_pln: number;
  fx_rate: string;
  fx_rate_source: string;
  direction: "debit" | "credit";
}
export interface FrozenOperation {
  kind: ImportTransactionKind;
  component: "main" | "fee";
  row_ids: string[];
  booking_date: string;
  purchase_date: string | null;
  description: string;
  quote: FrozenQuote;
  postings: FrozenPosting[];
}
export interface FrozenGroup {
  group_id: string;
  action: "create" | "link";
  operations: FrozenOperation[];
  transaction_id?: string;
  links?: {
    row_id: string;
    posting_id: string;
    component: "whole";
    attributed_source_amount: number;
  }[];
  card_statement?: {
    source_id: string;
    account_id: string;
    data: Record<string, unknown>;
  };
}
export interface ImportPreview {
  id: string;
  batch_id: string;
  version: number;
  request_hash: string;
  groups: FrozenGroup[];
  quotes: FrozenQuote[];
  new_transaction_count: number;
  linked_count: number;
  unresolved_count: number;
  warnings: string[];
}
export interface CommitRequest {
  preview_id: string;
  request_hash: string;
}
export interface CommitResult {
  receipt_id: string;
  batch_id: string;
  request_hash: string;
  transaction_ids: string[];
  linked_row_ids: string[];
  remaining_group_ids: string[];
  commit_state: ImportBatch["commit_state"];
}
export interface DecisionUpdate {
  expected_version: number;
  decisions: ImportDecision[];
}
export interface PreviewRequest {
  expected_version: number;
  group_ids: string[];
  acknowledgements: string[];
}
export interface RowFilters {
  source_id?: string;
  revision_id?: string;
  offset?: number;
  limit?: number;
}
interface Keyed {
  idempotencyKey: string;
}

const root = "/finance/imports";
const path = (id: string) => `${root}/${encodeURIComponent(id)}`;
const headers = (input: Keyed) => ({ "Idempotency-Key": input.idempotencyKey });
export const importQueryKey = (actor: ProcessingActor, ...parts: unknown[]) =>
  ["finance", "imports", actor.ownerId, actor.generation, ...parts] as const;
export function useImportActor(): ProcessingActor {
  const ownerId = useAuthStore((state) => state.user?.id ?? null);
  const generation = useDocumentProcessingStore((state) => state.generation);
  return { ownerId, generation };
}
function assertActor(actor: ProcessingActor) {
  if (!isProcessingActorCurrent(actor))
    throw new Error("Sesja importu zmieniła się. Otwórz import ponownie.");
}
async function guarded<T>(
  actor: ProcessingActor,
  operation: () => Promise<T>,
): Promise<T> {
  assertActor(actor);
  const value = await operation();
  assertActor(actor);
  return value;
}
function useImportMutation<Input, Output>(
  operation: (input: Input, actor: ProcessingActor) => Promise<Output>,
  ledger = false,
) {
  const client = useQueryClient();
  const actor = useImportActor();
  const lastActor = useRef<ProcessingActor>();
  const mutation = useMutation({
    retry: false,
    onMutate: () => {
      assertActor(actor);
      lastActor.current = captureProcessingActor();
      return actor;
    },
    mutationFn: (input: Input) => guarded(actor, () => operation(input, actor)),
    onSuccess: (_result, _input, context) => {
      if (!isProcessingActorCurrent(context)) return;
      client.invalidateQueries({ queryKey: importQueryKey(context) });
      if (ledger) invalidateFinanceLedger(client);
    },
  });
  return {
    ...mutation,
    data: isProcessingActorCurrent(lastActor.current)
      ? mutation.data
      : undefined,
  };
}

export function useImports() {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, "list"),
    enabled: !!actor.ownerId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () => (await api.get<ImportBatch[]>(root, { signal })).data,
      ),
  });
}

export function useImportAccounts() {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, "mapping", "accounts"),
    enabled: !!actor.ownerId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (await api.get<Account[]>("/finance/accounts", { signal })).data,
      ),
  });
}
export function useImportCategories() {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, "mapping", "categories"),
    enabled: !!actor.ownerId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (await api.get<Category[]>("/finance/categories", { signal })).data,
      ),
  });
}
export function useImport(batchId: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, batchId),
    enabled: !!actor.ownerId && !!batchId,
    retry: false,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (await api.get<ImportBatch>(path(batchId!), { signal })).data,
      ),
    refetchInterval: (query) =>
      query.state.data?.sources.some((source) =>
        ["queued", "processing"].includes(source.processing_state),
      )
        ? 3000
        : false,
  });
}
export function useImportRows(
  batchId: string | null,
  filters: RowFilters = {},
  publication: string | number = "",
) {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, batchId, "rows", filters, publication),
    enabled: !!actor.ownerId && !!batchId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<ImportRowPage>(`${path(batchId!)}/rows`, {
              params: filters,
              signal,
            })
          ).data,
      ),
  });
}
export function useImportCandidates(batchId: string, rowId: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, batchId, "candidates", rowId),
    enabled: !!actor.ownerId && !!rowId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<ExistingCandidate[]>(
              `${path(batchId)}/rows/${encodeURIComponent(rowId!)}/candidates`,
              { signal },
            )
          ).data,
      ),
  });
}

export function useImportExistingTransaction(
  batchId: string,
  transactionId: string | null,
) {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(
      actor,
      batchId,
      "existing-transaction",
      transactionId,
    ),
    enabled: !!actor.ownerId && !!transactionId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<Transaction>(
              `/finance/transactions/${encodeURIComponent(transactionId!)}`,
              { signal },
            )
          ).data,
      ),
  });
}
export function useCreateImport() {
  return useImportMutation(
    async (input: Keyed & { kind: ImportKind }) =>
      (
        await api.post<ImportBatch>(
          root,
          { kind: input.kind },
          { headers: headers(input) },
        )
      ).data,
  );
}
export function useUploadImportSource() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; file: File }) => {
      const form = new FormData();
      form.append("file", input.file);
      return (
        await api.post<ImportUploadResult>(
          `${path(input.batchId)}/sources`,
          form,
          {
            headers: {
              ...headers(input),
              "Content-Type": "multipart/form-data",
            },
          },
        )
      ).data;
    },
  );
}
export function useAttachImportDocument() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; documentId: string }) =>
      (
        await api.post<ImportUploadResult>(
          `${path(input.batchId)}/sources/existing`,
          { document_id: input.documentId },
          { headers: headers(input) },
        )
      ).data,
  );
}
export function usePrepareImportSource() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; sourceId: string }) =>
      (
        await api.post<ImportJob>(
          `${path(input.batchId)}/sources/${encodeURIComponent(input.sourceId)}/prepare`,
          null,
          { headers: headers(input) },
        )
      ).data,
  );
}
export function useSaveImportDecisions() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; data: DecisionUpdate }) =>
      (
        await api.put<ImportBatch>(
          `${path(input.batchId)}/decisions`,
          input.data,
          { headers: headers(input) },
        )
      ).data,
  );
}
export function usePreviewImport() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; data: PreviewRequest }) =>
      (
        await api.post<ImportPreview>(
          `${path(input.batchId)}/preview`,
          input.data,
          { headers: headers(input) },
        )
      ).data,
  );
}
export function useCommitImport() {
  return useImportMutation(
    async (input: Keyed & { batchId: string; data: CommitRequest }, actor) => {
      const verify = (value: CommitResult): CommitResult => {
        if (
          value.batch_id !== input.batchId ||
          value.request_hash !== input.data.request_hash ||
          !value.receipt_id
        )
          throw new Error(
            "Nie można potwierdzić wyniku tej decyzji. Sprawdź zapisane potwierdzenie.",
          );
        return value;
      };
      try {
        return verify(
          (
            await api.post<CommitResult>(
              `${path(input.batchId)}/commit`,
              input.data,
              { headers: headers(input) },
            )
          ).data,
        );
      } catch (error) {
        assertActor(actor);
        const status = (error as AxiosError).response?.status;
        if (status && status < 500 && status !== 408) throw error;
        try {
          return verify(
            (
              await api.get<CommitResult>(
                `${path(input.batchId)}/commands/${encodeURIComponent(input.idempotencyKey)}`,
              )
            ).data,
          );
        } catch {
          throw error;
        }
      }
    },
    true,
  );
}
export function useImportCommandResult(batchId: string, key: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: importQueryKey(actor, batchId, "command", key),
    enabled: !!actor.ownerId && !!key,
    retry: false,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<CommitResult>(
              `${path(batchId)}/commands/${encodeURIComponent(key!)}`,
              { signal },
            )
          ).data,
      ),
  });
}
export function useArchiveImport() {
  return useImportMutation(
    async (input: Keyed & { batchId: string }) =>
      (
        await api.post<ImportBatch>(`${path(input.batchId)}/archive`, null, {
          headers: headers(input),
        })
      ).data,
  );
}
export function importError(error: unknown): string {
  const data = (
    error as AxiosError<{ detail?: string; code?: string }> | undefined
  )?.response?.data;
  return (
    data?.detail ??
    data?.code ??
    (error instanceof Error
      ? error.message
      : "Nie udało się wykonać operacji importu.")
  );
}
