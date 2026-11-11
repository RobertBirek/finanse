import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import api from "../lib/api";
import {
  assertActor,
  guarded,
  useImportActor,
  useImportMutation,
  type SourcePosition,
} from "./bankImports";
import type { Loan, LoanDetail, LoanInput } from "./loans";
import type { ProcessingActor } from "../stores/documentProcessingStore";

export interface ScheduleRow {
  bank_number: number;
  due_date: string;
  principal: number;
  interest: number;
  fees: number;
  total: number;
  balance_after: number | null;
  position: SourcePosition;
}
export type ScheduleTargetData = {
  loan_id: string | null;
  new_loan: LoanInput | null;
};
export interface ScheduleDifference {
  cutover_date: string;
  reused_ids: string[];
  new_rows: ScheduleRow[];
  superseded_ids: string[];
  retained_history_ids: string[];
  conflicts: {
    code: string;
    row_key: string | null;
    installment_ids: string[];
  }[];
  warnings: string[];
  fingerprint: string;
}
export interface SchedulePreview {
  id: string;
  batch_id: string;
  version: number;
  request_hash: string;
  source_revision_id: string;
  target: ScheduleTargetData;
  cutover_date: string;
  loan_fingerprint: string;
  diff: ScheduleDifference;
  ledger_effect: "none";
  bank_effective_date?: string | null;
}
export interface SchedulePreviewRequest {
  expected_version: number;
  source_id: string;
  target: ScheduleTargetData;
  acknowledgements: string[];
}
export interface ScheduleResult {
  receipt_id: string;
  batch_id: string;
  request_hash: string;
  loan_id: string;
  revision_id: string;
  reused_ids: string[];
  new_ids: string[];
  superseded_ids: string[];
  ledger_changed: false;
}
export interface ScheduleRevision {
  id: string;
  loan_id: string;
  ordinal: number;
  kind: "manual_baseline" | "bank_import";
  state: "active" | "superseded";
  previous_revision_id: string | null;
  source_revision_id: string | null;
  receipt_id: string;
  bank_effective_date: string | null;
  activated_on: string;
  cutover_date: string;
  document_id: string | null;
  original_name: string | null;
  batch_id: string | null;
}
export interface ScheduleRevisionDetail extends ScheduleRevision {
  installments: {
    installment_id: string;
    bank_number: number | null;
    source_row_id: string | null;
    due_date: string;
    principal_pln: number;
    interest_pln: number;
    fees_pln: number;
    balance_after_pln: number | null;
  }[];
}
const importPath = (id: string) => `/finance/imports/${encodeURIComponent(id)}`;
const loanPath = (id: string) => `/finance/loans/${encodeURIComponent(id)}`;
export const scheduleKey = (actor: ProcessingActor, ...parts: unknown[]) =>
  [
    "finance",
    "loanSchedules",
    actor.ownerId,
    actor.generation,
    ...parts,
  ] as const;
export function invalidateScheduleQueries(
  client: ReturnType<typeof useQueryClient>,
  actor: ProcessingActor,
) {
  assertActor(actor);
  void client.invalidateQueries({ queryKey: ["finance", "loans"] });
  void client.invalidateQueries({ queryKey: scheduleKey(actor) });
}
export function useScheduleLoans() {
  const actor = useImportActor();
  return useQuery({
    queryKey: scheduleKey(actor, "targets"),
    enabled: !!actor.ownerId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () => (await api.get<Loan[]>("/finance/loans", { signal })).data,
      ),
  });
}
export function useScheduleLoan(id: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: scheduleKey(actor, "target", id),
    enabled: !!actor.ownerId && !!id,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () => (await api.get<LoanDetail>(loanPath(id!), { signal })).data,
      ),
  });
}
export function useSchedulePreview() {
  return useImportMutation(
    async (input: {
      batchId: string;
      data: SchedulePreviewRequest;
      idempotencyKey: string;
    }) =>
      (
        await api.post<SchedulePreview>(
          `${importPath(input.batchId)}/schedule-preview`,
          input.data,
          { headers: { "Idempotency-Key": input.idempotencyKey } },
        )
      ).data,
  );
}
export function validScheduleResult(
  value: ScheduleResult,
  batchId: string,
  hash: string,
) {
  if (
    value.batch_id !== batchId ||
    value.request_hash !== hash ||
    !value.receipt_id ||
    !value.loan_id ||
    !value.revision_id ||
    value.ledger_changed !== false
  )
    throw new Error("Nie można potwierdzić wyniku tej decyzji harmonogramu.");
  return value;
}
export function useActivateSchedule() {
  const client = useQueryClient();
  return useImportMutation(
    async (
      input: {
        batchId: string;
        data: { preview_id: string; request_hash: string };
        idempotencyKey: string;
      },
      actor,
    ) => {
      let value: ScheduleResult;
      try {
        value = (
          await api.post<ScheduleResult>(
            `${importPath(input.batchId)}/activate-schedule`,
            input.data,
            { headers: { "Idempotency-Key": input.idempotencyKey } },
          )
        ).data;
      } catch (error) {
        assertActor(actor);
        const status = (error as AxiosError).response?.status;
        if (status && status < 500 && status !== 408) throw error;
        try {
          value = (
            await api.get<ScheduleResult>(
              `${importPath(input.batchId)}/commands/${encodeURIComponent(input.idempotencyKey)}`,
            )
          ).data;
        } catch {
          throw error;
        }
      }
      assertActor(actor);
      const result = validScheduleResult(
        value,
        input.batchId,
        input.data.request_hash,
      );
      invalidateScheduleQueries(client, actor);
      return result;
    },
  );
}
export function useScheduleCommandResult(batchId: string, key: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: scheduleKey(actor, "command", batchId, key),
    enabled: !!actor.ownerId && !!key,
    retry: false,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<ScheduleResult>(
              `${importPath(batchId)}/commands/${encodeURIComponent(key!)}`,
              { signal },
            )
          ).data,
      ),
  });
}
export function useLoanScheduleRevisions(loanId: string | null) {
  const actor = useImportActor();
  return useQuery({
    queryKey: scheduleKey(actor, "history", loanId),
    enabled: !!actor.ownerId && !!loanId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<ScheduleRevision[]>(
              `${loanPath(loanId!)}/schedule-revisions`,
              { signal },
            )
          ).data,
      ),
  });
}
export function useLoanScheduleRevision(
  loanId: string | null,
  revisionId: string | null,
) {
  const actor = useImportActor();
  return useQuery({
    queryKey: scheduleKey(actor, "history", loanId, revisionId),
    enabled: !!actor.ownerId && !!loanId && !!revisionId,
    queryFn: ({ signal }) =>
      guarded(
        actor,
        async () =>
          (
            await api.get<ScheduleRevisionDetail>(
              `${loanPath(loanId!)}/schedule-revisions/${encodeURIComponent(revisionId!)}`,
              { signal },
            )
          ).data,
      ),
  });
}
