import { useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { Account } from "../../api/finance";
import {
  refreshOpeningBalanceAccount,
  useUpdateOpeningBalance,
  type OpeningBalanceView,
} from "../../api/openingBalances";
import {
  openingBalanceDraft,
  openingBalancePayload,
} from "../../lib/openingBalances";
import { formatCalendarDate } from "../../lib/date";
import { formatPLN } from "../../lib/format";
import { useAuthStore } from "../../stores/authStore";
import { apiErrorDetail, isConflict } from "./accountSettings";
import { OpeningBalanceFields } from "./OpeningBalanceFields";

export function AccountOpeningBalance({ account }: { account: Account }) {
  const [editing, setEditing] = useState(false);
  const value = account.opening_balance;
  if (!value) return null; // Fail closed for an old/uninitialized API response.
  return (
    <div className="mt-3 min-w-0">
      <p className="text-sm text-gray-300">
        BO: {formatPLN(value.amount_minor)} {account.currency} ·{" "}
        {formatCalendarDate(value.date)}
      </p>
      {value.can_edit ? (
        editing ? (
          <OpeningBalanceEditor
            key={account.id}
            account={account}
            initial={value}
            onClose={() => setEditing(false)}
          />
        ) : (
          <button
            type="button"
            className="btn-secondary mt-2 text-sm"
            aria-label={`Edytuj BO konta ${account.name}`}
            onClick={() => setEditing(true)}
          >
            Edytuj BO
          </button>
        )
      ) : (
        <p className="mt-1 text-xs text-gray-400">
          {value.blocked_reason ??
            "Konto ma inne transakcje — BO jest zablokowany."}
        </p>
      )}
    </div>
  );
}

function OpeningBalanceEditor({
  account,
  initial,
  onClose,
}: {
  account: Account;
  initial: OpeningBalanceView;
  onClose: () => void;
}) {
  const [scope] = useState(() => ({
    id: account.id,
    session: useAuthStore.getState().sessionVersion,
    userId: useAuthStore.getState().user?.id ?? "",
  }));
  const session = useAuthStore((state) => state.sessionVersion);
  const userId = useAuthStore((state) => state.user?.id);
  const [snapshot, setSnapshot] = useState(initial);
  const [currency, setCurrency] = useState(account.currency);
  const [draft, setDraft] = useState(() => openingBalanceDraft(initial));
  const [failure, setFailure] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [needsConfirmation, setNeedsConfirmation] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const intent = useRef<{ serialized: string; key: string } | null>(null);
  const mutation = useUpdateOpeningBalance();
  const client = useQueryClient();
  const active =
    session === scope.session &&
    userId === scope.userId &&
    account.id === scope.id;
  const busy = mutation.isPending || refreshing;
  const payload = openingBalancePayload(draft, currency);
  function isActiveNow() {
    return (
      account.id === scope.id &&
      useAuthStore.getState().sessionVersion === scope.session &&
      useAuthStore.getState().user?.id === scope.userId
    );
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (
      !isActiveNow() ||
      busy ||
      conflict ||
      !snapshot.can_edit ||
      !payload ||
      (needsConfirmation && !confirmed)
    )
      return;
    const body = { ...payload, expected_version: snapshot.version };
    const serialized = JSON.stringify(body);
    if (intent.current?.serialized !== serialized)
      intent.current = { serialized, key: crypto.randomUUID() };
    setFailure(null);
    mutation.mutate(
      {
        ...body,
        id: scope.id,
        key: intent.current.key,
        session: scope.session,
        userId: scope.userId,
      },
      {
        onSuccess: () => {
          if (isActiveNow()) onClose();
        },
        onError: (error) => {
          if (!isActiveNow()) return;
          setFailure(apiErrorDetail(error));
          if (isConflict(error)) {
            setConflict(true);
            setConfirmed(false);
            client.invalidateQueries({ queryKey: ["finance", "accounts"] });
          }
        },
      },
    );
  }
  async function refresh() {
    if (!isActiveNow() || busy) return;
    setRefreshing(true);
    try {
      const fresh = await refreshOpeningBalanceAccount(
        scope.id,
        scope.session,
        scope.userId,
      );
      if (!isActiveNow() || !fresh.opening_balance) return;
      setSnapshot(fresh.opening_balance);
      setCurrency(fresh.currency);
      setDraft(openingBalanceDraft(fresh.opening_balance));
      setConflict(false);
      setFailure(null);
      setNeedsConfirmation(true);
      setConfirmed(false);
      intent.current = null;
      client.invalidateQueries({ queryKey: ["finance", "accounts"] });
    } catch (error) {
      if (isActiveNow()) setFailure(apiErrorDetail(error));
    } finally {
      setRefreshing(false);
    }
  }
  return (
    <form
      aria-label={`Bilans otwarcia konta ${account.name}`}
      onSubmit={submit}
      className="mt-3 min-w-0 rounded-lg border border-gray-700 p-3"
    >
      {!active ? (
        <p role="alert" className="text-sm text-red-400">
          Sesja lub konto zmieniły się. Zamknij edycję BO i odśwież dane.
        </p>
      ) : null}
      <OpeningBalanceFields
        value={draft}
        onChange={setDraft}
        currency={currency}
        disabled={busy || !active || conflict || !snapshot.can_edit}
      />
      {failure ? (
        <p role="alert" className="mt-2 text-sm text-red-400">
          {failure}
        </p>
      ) : null}
      {!snapshot.can_edit ? (
        <p className="mt-2 text-sm text-gray-400">{snapshot.blocked_reason}</p>
      ) : null}
      {conflict ? (
        <button
          type="button"
          className="btn-secondary mt-2"
          disabled={busy || !active}
          onClick={() => void refresh()}
        >
          Odśwież BO
        </button>
      ) : null}
      {needsConfirmation && snapshot.can_edit ? (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={confirmed}
            disabled={busy || !active}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          Potwierdzam zmianę bilansu otwarcia
        </label>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="submit"
          className="btn-primary"
          disabled={
            busy ||
            !active ||
            conflict ||
            !snapshot.can_edit ||
            !payload ||
            (needsConfirmation && !confirmed)
          }
        >
          Zapisz BO
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={onClose}
        >
          Anuluj BO
        </button>
      </div>
    </form>
  );
}
