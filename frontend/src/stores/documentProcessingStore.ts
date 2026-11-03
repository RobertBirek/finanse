import { create } from "zustand";
import type { DocumentData } from "../api/documents";
import {
  getDocumentOperations,
  getOperationNotice,
  isActiveOperation,
  type ProcessingNotice,
  type ProcessingOperation,
} from "../components/documents/documentProcessing";
import { useAuthStore } from "./authStore";

export type ProcessingActor = { ownerId: string | null; generation: number };
export type ProcessingWatchInput = {
  key: string;
  documentId: string;
  operationId?: string;
  source: ProcessingOperation["source"];
  kind: ProcessingOperation["kind"];
};
export type ProcessingWatch = ProcessingWatchInput & {
  sequence: number;
  state: string;
};
export type ProcessingToast = ProcessingNotice & {
  id: string;
  documentId: string;
};

type ProcessingState = {
  ownerId: string | null;
  generation: number;
  sequence: number;
  completionCount: number;
  watches: Record<string, ProcessingWatch>;
  toasts: ProcessingToast[];
  seen: Record<string, true>;
  completedLegacyAt: Record<string, number>;
  bindOwner: (ownerId: string | null) => void;
  register: (actor: ProcessingActor, watch: ProcessingWatchInput) => void;
  observeDocument: (
    actor: ProcessingActor,
    document: DocumentData,
    requestSequence: number,
  ) => void;
  forgetDocument: (actor: ProcessingActor, documentId: string) => void;
  markUnknown: (actor: ProcessingActor, documentId?: string) => void;
  dismiss: (id: string) => void;
};

function matches(state: ProcessingState, actor: ProcessingActor): boolean {
  return (
    actor.ownerId !== null &&
    state.ownerId === actor.ownerId &&
    state.generation === actor.generation
  );
}

export const useDocumentProcessingStore = create<ProcessingState>((set) => ({
  ownerId: null,
  generation: 0,
  sequence: 0,
  completionCount: 0,
  watches: {},
  toasts: [],
  seen: {},
  completedLegacyAt: {},
  bindOwner: (ownerId) =>
    set((state) =>
      state.ownerId === ownerId
        ? state
        : {
            ownerId,
            generation: state.generation + 1,
            sequence: state.sequence + 1,
            completionCount: 0,
            watches: {},
            toasts: [],
            seen: {},
            completedLegacyAt: {},
          },
    ),
  register: (actor, watch) =>
    set((state) => {
      if (!matches(state, actor) || state.watches[watch.key]) return state;
      if (
        watch.source !== "legacy_ocr" &&
        watch.operationId &&
        state.seen[watch.operationId]
      )
        return state;
      const sequence = state.sequence + 1;
      return {
        sequence,
        watches: {
          ...state.watches,
          [watch.key]: { ...watch, sequence, state: "pending" },
        },
      };
    }),
  observeDocument: (actor, document, requestSequence) =>
    set((state) => {
      if (!matches(state, actor) || document.user_id !== actor.ownerId)
        return state;
      const operations = getDocumentOperations(document);
      const watches = { ...state.watches },
        seen = { ...state.seen };
      const toasts = [...state.toasts];
      const completedLegacyAt = { ...state.completedLegacyAt };
      let sequence = state.sequence,
        completions = 0,
        changed = false;
      for (const watch of Object.values(watches)) {
        if (
          watch.documentId !== document.id ||
          requestSequence < watch.sequence
        )
          continue;
        const operation = operations.find((op) =>
          watch.operationId
            ? op.id === watch.operationId
            : op.source === watch.source,
        );
        if (!operation) {
          delete watches[watch.key];
          changed = true;
          continue;
        }
        if (isActiveOperation(operation)) {
          const operationId = operation.id.startsWith("upload:")
            ? undefined
            : operation.id;
          if (
            watch.state !== operation.state ||
            watch.operationId !== operationId
          ) {
            watches[watch.key] = {
              ...watch,
              operationId,
              state: operation.state,
            };
            changed = true;
          }
          continue;
        }
        if (
          !["succeeded", "failed", "paused", "superseded"].includes(
            operation.state,
          )
        ) {
          if (watch.state !== "unknown") {
            watches[watch.key] = { ...watch, state: "unknown" };
            changed = true;
          }
          continue;
        }
        delete watches[watch.key];
        changed = true;
        completions += 1;
        const completionKey =
          operation.source === "legacy_ocr"
            ? `${operation.id}|${watch.key}`
            : operation.id;
        if (operation.source === "legacy_ocr") {
          completedLegacyAt[document.id] = Date.parse(document.updated_at);
        }
        if (!seen[completionKey]) {
          seen[completionKey] = true;
          const notice = getOperationNotice(operation);
          if (notice)
            toasts.push({
              ...notice,
              id: completionKey,
              documentId: document.id,
            });
        }
      }
      for (const operation of operations) {
        if (!isActiveOperation(operation)) continue;
        if (operation.source !== "legacy_ocr" && seen[operation.id]) continue;
        if (
          operation.source === "legacy_ocr" &&
          Date.parse(document.updated_at) <=
            (completedLegacyAt[document.id] ?? -Infinity)
        )
          continue;
        if (
          Object.values(watches).some(
            (w) =>
              w.documentId === document.id && w.source === operation.source,
          )
        )
          continue;
        const key =
          operation.source === "legacy_ocr"
            ? `${operation.id}:${document.updated_at}`
            : operation.id;
        sequence += 1;
        watches[key] = {
          key,
          documentId: document.id,
          source: operation.source,
          kind: operation.kind,
          operationId: operation.id.startsWith("upload:")
            ? undefined
            : operation.id,
          state: operation.state,
          sequence,
        };
        changed = true;
      }
      return changed
        ? {
            watches,
            seen,
            toasts,
            sequence,
            completionCount: state.completionCount + completions,
            completedLegacyAt,
          }
        : state;
    }),
  markUnknown: (actor, documentId) =>
    set((state) => {
      if (!matches(state, actor)) return state;
      let changed = false;
      const watches = Object.fromEntries(
        Object.entries(state.watches).map(([key, watch]) => {
          if (
            (!documentId || watch.documentId === documentId) &&
            watch.state !== "unknown"
          ) {
            changed = true;
            return [key, { ...watch, state: "unknown" }];
          }
          return [key, watch];
        }),
      );
      return changed ? { watches } : state;
    }),
  forgetDocument: (actor, documentId) =>
    set((state) => {
      if (!matches(state, actor)) return state;
      const watches = Object.fromEntries(
        Object.entries(state.watches).filter(
          ([, watch]) => watch.documentId !== documentId,
        ),
      );
      return Object.keys(watches).length === Object.keys(state.watches).length
        ? state
        : { watches };
    }),
  dismiss: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    })),
}));

// One subscription, outside React mounts: logout/same-user relogin fences late promises.
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id)
    useDocumentProcessingStore.getState().bindOwner(state.user?.id ?? null);
});

export function captureProcessingActor(): ProcessingActor {
  const ownerId = useAuthStore.getState().user?.id ?? null;
  useDocumentProcessingStore.getState().bindOwner(ownerId);
  return {
    ownerId,
    generation: useDocumentProcessingStore.getState().generation,
  };
}

export function isProcessingActorCurrent(
  actor: ProcessingActor | undefined,
): actor is ProcessingActor {
  return (
    !!actor &&
    actor.ownerId === useAuthStore.getState().user?.id &&
    matches(useDocumentProcessingStore.getState(), actor)
  );
}
