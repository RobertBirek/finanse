import { useRef, useState } from "react";
import type { AxiosError } from "axios";
import { Link } from "react-router-dom";
import {
  personError,
  useLinkGift,
  usePeople,
  usePersonLinkContext,
  useUnlinkGift,
  type PersonLinkContext,
} from "../../api/people";
import { useAuthStore } from "../../stores/authStore";
import { Dialog } from "../Dialog";
import { QueryFeedback } from "../QueryFeedback";

export function PersonGiftDialog({
  transactionId,
  onClose,
}: {
  transactionId: string;
  onClose: () => void;
}) {
  const context = usePersonLinkContext(transactionId);
  const assign = useLinkGift();
  const detach = useUnlinkGift();
  const [epoch, setEpoch] = useState(0);
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const busy = assign.isPending || detach.isPending;
  return (
    <Dialog
      label="Darczyńca"
      onClose={onClose}
      busy={busy}
      panelClassName="card max-w-lg w-full"
    >
      <h2 className="text-lg font-semibold mb-3">Darczyńca</h2>
      {!active ? (
        <p role="alert">
          Sesja zmieniła się. Zamknij okno i wczytaj aktualne dane.
        </p>
      ) : (
        <QueryFeedback
          loading={context.isLoading}
          error={context.isError}
          onRetry={context.refetch}
          errorMessage="Nie udało się pobrać powiązania osoby."
        >
          {context.data ? (
            <GiftForm
              key={`${transactionId}:${epoch}`}
              initial={context.data}
              session={session}
              assign={assign}
              detach={detach}
              onClose={onClose}
              onRefresh={async () => {
                const result = await context.refetch();
                if (result.isSuccess) setEpoch((value) => value + 1);
              }}
            />
          ) : null}
        </QueryFeedback>
      )}
      <button className="btn-secondary mt-4" disabled={busy} onClick={onClose}>
        Zamknij
      </button>
    </Dialog>
  );
}

function GiftForm({
  initial,
  session,
  assign,
  detach,
  onClose,
  onRefresh,
}: {
  initial: PersonLinkContext;
  session: number;
  assign: ReturnType<typeof useLinkGift>;
  detach: ReturnType<typeof useUnlinkGift>;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [snapshot] = useState(initial);
  const [personId, setPersonId] = useState("");
  const [offset, setOffset] = useState(0);
  const people = usePeople({ offset }, !snapshot.person && snapshot.eligible);
  const [failure, setFailure] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const intent = useRef<{ body: string; key: string } | null>(null);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const busy = assign.isPending || detach.isPending;
  function save(unlink: boolean) {
    if (busy || conflict || !active) return;
    const body = JSON.stringify({
      personId,
      unlink,
      snapshot: snapshot.snapshot,
    });
    if (intent.current?.body !== body)
      intent.current = { body, key: crypto.randomUUID() };
    const input = {
      id: snapshot.transaction_id,
      key: intent.current.key,
      expected_transaction_snapshot: snapshot.snapshot,
    };
    const callbacks = {
      onSuccess: () => {
        if (useAuthStore.getState().sessionVersion === session) onClose();
      },
      onError: (error: unknown) => {
        if (useAuthStore.getState().sessionVersion !== session) return;
        setFailure(personError(error));
        if ((error as AxiosError)?.response?.status === 409) setConflict(true);
      },
    };
    if (unlink) detach.mutate(input, callbacks);
    else assign.mutate({ ...input, person_id: personId }, callbacks);
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-400">
        Powiązanie osoby nie zmienia kwoty, kategorii ani salda rachunku.
      </p>
      {snapshot.person ? (
        <>
          <Link
            className="text-advisor-400 underline"
            to={`/finances/people/${snapshot.person.id}`}
          >
            {snapshot.person.name}
          </Link>
          <button
            className="btn-secondary block"
            disabled={busy || conflict || !active}
            onClick={() => save(true)}
          >
            Odepnij darczyńcę
          </button>
        </>
      ) : !snapshot.eligible ? (
        <p>{snapshot.reason}</p>
      ) : (
        <QueryFeedback
          loading={people.isLoading}
          error={people.isError}
          onRetry={people.refetch}
          errorMessage="Nie udało się pobrać osób."
        >
          <label className="block">
            Darczyńca
            <select
              className="input mt-1 w-full"
              value={personId}
              disabled={busy || conflict || !active}
              onChange={(e) => setPersonId(e.target.value)}
            >
              <option value="">Wybierz osobę</option>
              {people.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          {people.data?.total === 0 ? (
            <p>
              Dodaj osobę w sekcji{" "}
              <Link className="underline" to="/finances/people">
                Osoby
              </Link>
              .
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2 mt-3">
            <button
              className="btn-secondary"
              disabled={!offset || busy || conflict}
              onClick={() => {
                setOffset((v) => Math.max(0, v - 50));
                setPersonId("");
              }}
            >
              Poprzednie osoby
            </button>
            <button
              className="btn-secondary"
              disabled={
                !people.data ||
                offset + 50 >= people.data.total ||
                busy ||
                conflict
              }
              onClick={() => {
                setOffset((v) => v + 50);
                setPersonId("");
              }}
            >
              Następne osoby
            </button>
            <button
              className="btn-primary"
              disabled={!personId || busy || conflict || !active}
              onClick={() => save(false)}
            >
              Przypisz darczyńcę
            </button>
          </div>
        </QueryFeedback>
      )}
      {failure ? (
        <p role="alert" className="text-red-400">
          {failure}
        </p>
      ) : null}
      {conflict ? (
        <button className="btn-secondary" disabled={busy} onClick={onRefresh}>
          Odśwież dane
        </button>
      ) : null}
    </div>
  );
}
