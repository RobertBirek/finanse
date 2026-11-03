import { useEffect, useRef } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DocumentData } from "../../api/documents";
import api from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import {
  useDocumentProcessingStore,
  type ProcessingActor,
} from "../../stores/documentProcessingStore";
import { ProcessingFeedback } from "./ProcessingFeedback";

const POLL_MS = 3000;
const PAGE_SIZE = 100;

export function DocumentProcessingMonitor() {
  const ownerId = useAuthStore((s) => s.user?.id ?? null);
  const authenticated = useAuthStore((s) => s.authStatus === "authenticated");
  const generation = useDocumentProcessingStore((s) => s.generation);
  const boundOwner = useDocumentProcessingStore((s) => s.ownerId);
  const watches = useDocumentProcessingStore((s) => s.watches);
  const completionCount = useDocumentProcessingStore((s) => s.completionCount);
  const queryClient = useQueryClient();
  const actor: ProcessingActor = { ownerId, generation };
  const enabled = !!ownerId && authenticated && boundOwner === ownerId;
  const currentWatches = enabled ? Object.values(watches) : [];
  useEffect(() => {
    useDocumentProcessingStore.getState().bindOwner(ownerId);
  }, [ownerId]);
  const active = useQuery({
    queryKey: ["documents", "activity", ownerId, generation],
    enabled,
    retry: false,
    queryFn: async ({ signal }) => {
      const sequence = useDocumentProcessingStore.getState().sequence;
      const documents: DocumentData[] = [];
      for (let offset = 0; ; offset += PAGE_SIZE) {
        const { data } = await api.get<DocumentData[]>("/documents/active", {
          params: { limit: PAGE_SIZE, offset },
          signal,
        });
        if (!Array.isArray(data)) throw new Error("invalid_processing_status");
        documents.push(...data);
        if (data.length < PAGE_SIZE) break;
      }
      return { actor, sequence, documents };
    },
    refetchInterval: (query) =>
      query.state.data?.documents.length || currentWatches.length
        ? POLL_MS
        : false,
  });
  useEffect(() => {
    if (!enabled) return;
    if (active.isError) {
      useDocumentProcessingStore
        .getState()
        .markUnknown({ ownerId, generation });
      return;
    }
    if (!active.data) return;
    for (const document of active.data.documents)
      useDocumentProcessingStore
        .getState()
        .observeDocument(active.data.actor, document, active.data.sequence);
  }, [active.data, active.isError, enabled, ownerId, generation]);
  const activeIds = new Set(
    active.data?.documents.map((document) => document.id) ?? [],
  );
  const ids = [...new Set(currentWatches.map((w) => w.documentId))]
    .filter((id) => !activeIds.has(id))
    .sort();
  const statuses = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["documents", "processing", ownerId, generation, id],
      enabled,
      retry: false,
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const sequence = useDocumentProcessingStore.getState().sequence;
        const { data } = await api.get<DocumentData>(`/documents/${id}`, {
          signal,
        });
        return { actor, sequence, document: data };
      },
      refetchOnMount: "always" as const,
      refetchInterval: POLL_MS,
    })),
  });
  useEffect(() => {
    if (!enabled) return;
    statuses.forEach((status, index) => {
      if (status.data && !status.isError)
        useDocumentProcessingStore
          .getState()
          .observeDocument(
            status.data.actor,
            status.data.document,
            status.data.sequence,
          );
      const error = status.error as { response?: { status?: number } } | null;
      if (error?.response?.status === 404)
        useDocumentProcessingStore
          .getState()
          .forgetDocument({ ownerId, generation }, ids[index]);
      else if (status.isError)
        useDocumentProcessingStore
          .getState()
          .markUnknown({ ownerId, generation }, ids[index]);
    });
  }, [statuses, enabled, ownerId, generation, ids]);
  const previousCompletion = useRef(completionCount);
  useEffect(() => {
    if (previousCompletion.current !== completionCount) {
      previousCompletion.current = completionCount;
      if (enabled)
        void queryClient.invalidateQueries({ queryKey: ["documents"] });
    }
  }, [completionCount, enabled, queryClient]);
  return (
    <ProcessingFeedback
      actor={actor}
      watches={currentWatches}
      hasError={enabled && (active.isError || statuses.some((q) => q.isError))}
    />
  );
}
