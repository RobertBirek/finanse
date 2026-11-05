import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import type { ReceiptBody, ReceiptItemsContext } from "./receiptItems";

export type ReceiptReadState =
  | "pending"
  | "preparing"
  | "dispatched"
  | "succeeded"
  | "failed"
  | "unknown"
  | "paused"
  | "cancelled"
  | "superseded";
export interface ReceiptReadProblem {
  key: string;
  code: string;
  line_index: number | null;
  discount_index: number | null;
  message: string;
  requires_ack: boolean;
}
export interface ReceiptReadProposal {
  body: ReceiptBody;
  problems: ReceiptReadProblem[];
  importable: boolean;
}
export interface ReceiptReadSource {
  document_id: string;
  name: string;
  mime_type: string;
  source_sha256: string;
  allowed: boolean;
  blocked_reason: string | null;
}
export interface ReceiptReadContext {
  bill_id: string;
  bill_version: number;
  state_version: number;
  enabled: boolean;
  blocked_reason: string | null;
  policy_epoch: number;
  provider: string | null;
  model: string | null;
  limits: Record<string, number>;
  sources: ReceiptReadSource[];
  next_source_cursor: string | null;
}
export interface ReceiptReadJob {
  id: string;
  bill_id: string;
  document_id: string;
  generation: number;
  version: number;
  state: ReceiptReadState;
  source_sha256: string;
  dispatched: boolean;
  extraction_id: string | null;
  error_code: string | null;
  can_cancel: boolean;
  poll_after_ms: number | null;
  created_at: string;
}
export interface ReceiptReadJobPage {
  items: ReceiptReadJob[];
  next_cursor: string | null;
}
export interface ReceiptReadExportPreview {
  document_id: string;
  source_sha256: string;
  export_snapshot: string;
  policy_epoch: number;
  provider: string;
  model: string;
  reread_of_job_id: string | null;
  limits: Record<string, number>;
  remaining_user_calls: number;
  remaining_global_calls: number;
  notice: string;
}
export interface ReceiptReadResult {
  job: ReceiptReadJob;
  extraction_id: string;
  payload_sha256: string;
  proposal: ReceiptReadProposal;
  payload?: {
    printed_total: string | null;
    currency: string | null;
    lines: Record<string, unknown>[];
    discounts: Record<string, unknown>[];
  };
  source_sha256: string;
  derivative_sha256: string;
  provider: string;
  model: string;
  prompt_version: string;
  schema_version: string;
  quality: "complete" | "partial" | "unsupported";
  created_at: string;
}
export interface ReceiptReadImportPreview {
  job_id: string;
  extraction_id: string;
  payload_sha256: string;
  bill_version: number;
  state_version: number;
  import_snapshot: string;
  will_replace_draft: boolean;
  proposal: ReceiptReadProposal;
}
export interface ReceiptReadEvidence {
  extraction_id: string;
  extraction_sha256: string;
  job_id: string;
  source_document_id: string;
  source_sha256: string;
  line_map: Record<
    string,
    {
      source_index: number;
      source_text?: string;
      basis?: string;
      original_field_sha256: Record<string, string>;
      edited_fields: string[];
    }
  >;
  discount_map: Record<
    string,
    {
      source_index: number;
      source_text?: string;
      kind?: string;
      original_field_sha256: Record<string, string>;
      edited_fields: string[];
    }
  >;
  pending_problems: ReceiptReadProblem[];
  acknowledgements: Record<string, string>;
}
export interface ReadRequest {
  session: number;
  billId: string;
  body: Record<string, unknown>;
  key?: string;
  jobId?: string;
}
const prefix = ["finance", "receipt-read"] as const;
function fence(session: number) {
  if (session !== useAuthStore.getState().sessionVersion)
    throw new Error("session_changed");
}
function root(billId: string) {
  return `/finance/bills/${billId}/items`;
}
function useReadQuery<T>(
  billId: string,
  part: string,
  path: string,
  enabled = true,
) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: [...prefix, session, billId, part, path],
    enabled: enabled && !!billId,
    retry: false,
    queryFn: async ({ signal }) => {
      fence(session);
      const { data } = await api.get<T>(root(billId) + path, { signal });
      fence(session);
      return data;
    },
  });
}
export function useReceiptReadContext(
  billId: string,
  sourceCursor: string | null = null,
) {
  return useReadQuery<ReceiptReadContext>(
    billId,
    "context",
    `/reads/context${sourceCursor ? `?source_cursor=${encodeURIComponent(sourceCursor)}` : ""}`,
  );
}
export function useReceiptReadHistory(
  billId: string,
  cursor: string | null = null,
) {
  return useReadQuery<ReceiptReadJobPage>(
    billId,
    "history",
    `/reads${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
}
export function useReceiptReadResult(billId: string, jobId: string | null) {
  return useReadQuery<ReceiptReadResult>(
    billId,
    "result",
    `/reads/${jobId}/result`,
    !!jobId,
  );
}
export function useReceiptReadJob(billId: string, jobId: string | null) {
  const session = useAuthStore((s) => s.sessionVersion);
  return useQuery({
    queryKey: [...prefix, session, billId, "job", jobId],
    enabled: !!jobId,
    retry: false,
    queryFn: async ({ signal }) => {
      fence(session);
      const { data } = await api.get<ReceiptReadJob>(
        root(billId) + `/reads/${jobId}`,
        { signal },
      );
      fence(session);
      return data;
    },
    refetchInterval: (q) => {
      const job = q.state.data;
      return job && ["pending", "preparing", "dispatched"].includes(job.state)
        ? (job.poll_after_ms ?? false)
        : false;
    },
  });
}

export async function fetchReceiptReadJob(
  session: number,
  billId: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<ReceiptReadJob> {
  fence(session);
  const { data } = await api.get<ReceiptReadJob>(
    `${root(billId)}/reads/${jobId}`,
    { signal },
  );
  fence(session);
  return data;
}
function useReadMutation<T>(action: string, write = false, importing = false) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (input: ReadRequest) => {
      fence(input.session);
      if (write && !input.key) throw new Error("idempotency_key_required");
      const path = action === "cancel" ? `reads/${input.jobId}/cancel` : action;
      const { data } = await api.post<T>(
        `${root(input.billId)}/${path}`,
        input.body,
        ...(write ? [{ headers: { "Idempotency-Key": input.key } }] : []),
      );
      fence(input.session);
      return data;
    },
    onSettled: (_data, _error, input) => {
      if (!write || input.session !== useAuthStore.getState().sessionVersion)
        return;
      client.invalidateQueries({
        queryKey: [...prefix, input.session, input.billId],
      });
      if (importing) {
        client.invalidateQueries({
          queryKey: ["finance", "receipt-items", input.session, input.billId],
        });
        client.invalidateQueries({
          queryKey: ["finance", "receipt-payment", input.session, input.billId],
        });
      }
    },
  });
}
export function usePreviewReceiptReadExport() {
  return useReadMutation<ReceiptReadExportPreview>("read-export-preview");
}
export function useStartReceiptRead() {
  return useReadMutation<ReceiptReadJob>("read-start", true);
}
export function useCancelReceiptRead() {
  return useReadMutation<ReceiptReadJob>("cancel", true);
}
export function usePreviewReceiptReadImport() {
  return useReadMutation<ReceiptReadImportPreview>("read-import-preview");
}
export function useImportReceiptRead() {
  return useReadMutation<ReceiptItemsContext>("read-import", true, true);
}
