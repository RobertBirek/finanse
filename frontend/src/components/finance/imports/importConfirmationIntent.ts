import { useAuthStore } from "../../../stores/authStore";

const prefix = "finance-import-confirmation:";

export interface ImportConfirmationIntent {
  key: string;
  previewId: string;
  requestHash: string;
}

export function readImportConfirmation(
  storageKey: string | null,
): ImportConfirmationIntent | null {
  if (!storageKey) return null;
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ImportConfirmationIntent> | null;
    return value &&
      typeof value.key === "string" &&
      value.key &&
      typeof value.previewId === "string" &&
      value.previewId &&
      typeof value.requestHash === "string" &&
      value.requestHash
      ? {
          key: value.key,
          previewId: value.previewId,
          requestHash: value.requestHash,
        }
      : null;
  } catch {
    return null;
  }
}

export function writeImportConfirmation(
  storageKey: string | null,
  intent: ImportConfirmationIntent | null,
) {
  if (!storageKey) return;
  try {
    if (intent) sessionStorage.setItem(storageKey, JSON.stringify(intent));
    else sessionStorage.removeItem(storageKey);
  } catch {
    // In-memory recovery is still available when the browser blocks storage.
  }
}

export function importConfirmationKey(
  ownerId: string | null,
  batchId: string,
): string | null {
  return ownerId ? `${prefix}${ownerId}:${batchId}` : null;
}

useAuthStore.subscribe((state, previous) => {
  if (!previous.user || state.sessionVersion === previous.sessionVersion)
    return;
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index--) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(prefix)) sessionStorage.removeItem(key);
    }
  } catch {
    // Browsers may disallow session storage.
  }
});
