import type { ReactNode } from "react";
import { Dialog } from "./Dialog";

export function ConfirmDialog({
  title,
  children,
  onCancel,
  onConfirm,
  pendingMessage,
  error,
}: {
  title: string;
  children: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  pendingMessage?: string;
  error?: string | null;
}) {
  const busy = pendingMessage !== undefined;
  return (
    <Dialog label={title} onClose={onCancel} busy={busy}>
      <h2>{title}</h2>
      <div className="mt-2 break-words text-sm text-gray-300">{children}</div>
      {pendingMessage && (
        <p role="status" className="mt-3 text-sm text-gray-400">
          {pendingMessage}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-red-400">
          {error}
        </p>
      )}
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          className="btn-secondary disabled:opacity-60"
          disabled={busy}
          onClick={onCancel}
        >
          Anuluj
        </button>
        <button
          type="button"
          className="btn-danger aria-disabled:opacity-60"
          aria-disabled={busy || undefined}
          onClick={() => {
            if (!busy) onConfirm();
          }}
        >
          {title}
        </button>
      </div>
    </Dialog>
  );
}
