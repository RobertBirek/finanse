import { useState, type FormEvent } from "react";
import {
  personError,
  useCreatePerson,
  useUpdatePerson,
  type Person,
} from "../../api/people";
import { useAccounts } from "../../api/finance";
import { useAuthStore } from "../../stores/authStore";
import { Dialog } from "../Dialog";
import { QueryFeedback } from "../QueryFeedback";

export function PersonEditor({
  initial,
  onClose,
}: {
  initial?: Person;
  onClose: () => void;
}) {
  const [snapshot] = useState(initial);
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const [name, setName] = useState(snapshot?.name ?? "");
  const [reference, setReference] = useState(
    snapshot?.reference_account_id ?? "",
  );
  const [failure, setFailure] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const accounts = useAccounts();
  const create = useCreatePerson();
  const update = useUpdatePerson();
  const busy = create.isPending || update.isPending;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !active || needsRefresh || !name.trim()) return;
    const data = { name: name.trim(), reference_account_id: reference || null };
    const callbacks = {
      onSuccess: () => {
        if (useAuthStore.getState().sessionVersion === session) onClose();
      },
      onError: (error: unknown) => {
        if (useAuthStore.getState().sessionVersion !== session) return;
        setFailure(personError(error));
        // Person creation has no receipt: don't risk duplicate identities after an ambiguous failure.
        setNeedsRefresh(true);
      },
    };
    if (snapshot)
      update.mutate(
        { id: snapshot.id, expected_version: snapshot.version, ...data },
        callbacks,
      );
    else create.mutate(data, callbacks);
  }
  return (
    <Dialog
      label={snapshot ? "Edytuj osobę" : "Dodaj osobę"}
      onClose={onClose}
      busy={busy}
      panelClassName="card max-w-lg w-full"
    >
      <h2 className="text-lg font-semibold mb-4">
        {snapshot ? "Edytuj osobę" : "Dodaj osobę"}
      </h2>
      {!active ? (
        <p role="alert">Sesja zmieniła się. Zamknij okno i odśwież dane.</p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            Nazwa osoby
            <input
              className="input w-full mt-1"
              required
              maxLength={200}
              value={name}
              disabled={busy || needsRefresh}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <QueryFeedback
            loading={accounts.isLoading}
            error={accounts.isError}
            onRetry={accounts.refetch}
            errorMessage="Nie udało się pobrać kont."
          >
            <label className="block">
              Skrót z konta informacyjnego
              <select
                className="input w-full mt-1"
                value={reference}
                disabled={busy || needsRefresh}
                onChange={(e) => setReference(e.target.value)}
              >
                <option value="">Bez skrótu</option>
                {accounts.data
                  ?.filter((a) => !a.is_budget_account)
                  .map((a) => (
                    <option value={a.id} key={a.id}>
                      {a.name}
                    </option>
                  ))}
              </select>
            </label>
          </QueryFeedback>
          <p className="text-sm text-gray-400">
            Skrót otwiera historię osoby. Nie zmienia konta ani jego salda.
          </p>
          {failure ? (
            <p role="alert" className="text-red-400">
              {failure} Zamknij okno i sprawdź aktualne dane przed kolejną
              próbą.
            </p>
          ) : null}
          <button
            className="btn-primary"
            disabled={
              busy ||
              needsRefresh ||
              !name.trim() ||
              accounts.isLoading ||
              accounts.isError
            }
          >
            Zapisz osobę
          </button>
        </form>
      )}
      <button className="btn-secondary mt-3" disabled={busy} onClick={onClose}>
        Anuluj
      </button>
    </Dialog>
  );
}
