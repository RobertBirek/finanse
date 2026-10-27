import { useRef, useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { Account, AccountUpdateInput } from "../../api/finance";
import { ACCOUNT_TYPES, apiErrorDetail, isConflict } from "./accountSettings";

const ACCOUNT_DELETE_CONFLICT_MESSAGE =
  "Konto ma zapisy — zdezaktywuj je zamiast usuwać";

function accountTypeLabel(type: string): string {
  return ACCOUNT_TYPES.find((option) => option.value === type)?.label ?? type;
}

type AccountRowProps = {
  account: Account;
  updateMutation: UseMutationResult<
    Account,
    Error,
    AccountUpdateInput & { id: string }
  >;
  deleteMutation: UseMutationResult<void, Error, string>;
  editing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
};

export function AccountRow({
  account,
  updateMutation,
  deleteMutation,
  editing,
  onStartEdit,
  onCancelEdit,
}: AccountRowProps) {
  const [draftName, setDraftName] = useState(account.name);
  const [draftType, setDraftType] = useState(account.type);
  const [draftBudget, setDraftBudget] = useState(account.is_budget_account);
  const [draftIban, setDraftIban] = useState(account.iban ?? "");
  const [draftBankName, setDraftBankName] = useState(account.bank_name ?? "");
  const [draftHolder, setDraftHolder] = useState(account.account_holder ?? "");
  const [draftBic, setDraftBic] = useState(account.bic ?? "");
  const [draftNotes, setDraftNotes] = useState(account.notes ?? "");
  const [showIban, setShowIban] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"success" | "manual" | null>(
    null,
  );
  const copyAttempt = useRef(0);

  const rowPending =
    (updateMutation.isPending && updateMutation.variables?.id === account.id) ||
    (deleteMutation.isPending && deleteMutation.variables === account.id);

  const updateErrorForRow =
    updateMutation.variables?.id === account.id
      ? apiErrorDetail(updateMutation.error)
      : null;
  const deleteErrorForRow =
    deleteMutation.variables === account.id
      ? isConflict(deleteMutation.error)
        ? ACCOUNT_DELETE_CONFLICT_MESSAGE
        : apiErrorDetail(deleteMutation.error)
      : null;

  function startEdit() {
    setDraftName(account.name);
    setDraftType(account.type);
    setDraftBudget(account.is_budget_account);
    setDraftIban(account.iban ?? "");
    setDraftBankName(account.bank_name ?? "");
    setDraftHolder(account.account_holder ?? "");
    setDraftBic(account.bic ?? "");
    setDraftNotes(account.notes ?? "");
    onStartEdit();
  }

  function save() {
    updateMutation.mutate(
      {
        id: account.id,
        name: draftName,
        type: draftType,
        is_budget_account: draftBudget,
        ...(draftIban !== (account.iban ?? "")
          ? { iban: draftIban.trim() || null }
          : {}),
        ...(draftBankName !== (account.bank_name ?? "")
          ? { bank_name: draftBankName.trim() || null }
          : {}),
        ...(draftHolder !== (account.account_holder ?? "")
          ? { account_holder: draftHolder.trim() || null }
          : {}),
        ...(draftBic !== (account.bic ?? "")
          ? { bic: draftBic.trim() || null }
          : {}),
        ...(draftNotes !== (account.notes ?? "")
          ? { notes: draftNotes.trim() || null }
          : {}),
      },
      { onSuccess: onCancelEdit },
    );
  }

  function toggle() {
    updateMutation.mutate({ id: account.id, is_active: !account.is_active });
  }

  function remove() {
    if (window.confirm(`Usunąć konto "${account.name}"?`)) {
      deleteMutation.mutate(account.id);
    }
  }

  async function copyIban() {
    const attempt = ++copyAttempt.current;

    if (!navigator.clipboard?.writeText) {
      setShowIban(true);
      setCopyStatus("manual");
      return;
    }

    try {
      await navigator.clipboard.writeText(account.iban!);
      if (copyAttempt.current === attempt) {
        setCopyStatus("success");
      }
    } catch {
      if (copyAttempt.current === attempt) {
        setShowIban(true);
        setCopyStatus("manual");
      }
    }
  }

  function toggleIban() {
    if (showIban) {
      copyAttempt.current += 1;
      setCopyStatus(null);
    }
    setShowIban(!showIban);
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-800/40 p-3">
      <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="min-w-0 break-words text-sm font-medium text-white [overflow-wrap:anywhere]">
              {account.name}
            </p>
            {account.is_budget_account ? (
              <span className="rounded-sm bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400">
                budżetowe
              </span>
            ) : null}
            {!account.is_active ? (
              <span className="rounded-sm bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-500">
                nieaktywne
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            {accountTypeLabel(account.type)} · {account.currency}
          </p>
          {account.type !== "cash" && account.iban ? (
            <>
              <p className="mt-1 text-xs text-gray-500">
                {showIban
                  ? account.iban
                  : `•••• ${account.iban.replace(/\s/g, "").slice(-4)}`}{" "}
                <button
                  type="button"
                  className="ml-2 text-advisor-700"
                  onClick={toggleIban}
                >
                  {showIban ? "Ukryj" : "Pokaż"}
                </button>
                <button
                  type="button"
                  className="ml-2 text-advisor-700"
                  onClick={() => void copyIban()}
                >
                  Kopiuj
                </button>
              </p>
              {copyStatus ? (
                <p
                  className="mt-1 text-xs text-gray-500"
                  role="status"
                  aria-live="polite"
                >
                  {copyStatus === "success"
                    ? "Numer rachunku został skopiowany."
                    : "Nie udało się skopiować numeru rachunku. Skopiuj go ręcznie."}
                </p>
              ) : null}
              {copyStatus === "manual" && showIban ? (
                <input
                  aria-label="Numer rachunku do ręcznego skopiowania"
                  className="input mt-2 w-full font-mono text-xs"
                  readOnly
                  value={account.iban}
                  onFocus={(event) => event.currentTarget.select()}
                />
              ) : null}
            </>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {editing ? (
            <>
              <button
                type="button"
                aria-label={`Zapisz konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={save}
              >
                Zapisz
              </button>
              <button
                type="button"
                aria-label={`Anuluj edycję konta ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                onClick={onCancelEdit}
              >
                Anuluj
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                aria-label={`Edytuj konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={rowPending}
                onClick={startEdit}
              >
                Edytuj
              </button>
              <button
                type="button"
                aria-label={`${
                  account.is_active ? "Dezaktywuj" : "Aktywuj"
                } konto ${account.name}`}
                className="btn-secondary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rowPending}
                onClick={toggle}
              >
                {account.is_active ? "Dezaktywuj" : "Aktywuj"}
              </button>
              <button
                type="button"
                aria-label={`Usuń konto ${account.name}`}
                className="btn-danger px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={rowPending}
                onClick={remove}
              >
                Usuń
              </button>
            </>
          )}
        </div>
      </div>
      {editing ? (
        <div className="mt-3 space-y-3">
          <div>
            <label
              htmlFor="account-edit-name"
              className="mb-1 block text-xs text-gray-400"
            >
              Nazwa
            </label>
            <input
              id="account-edit-name"
              className="input"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="account-edit-type"
                className="mb-1 block text-xs text-gray-400"
              >
                Typ
              </label>
              <select
                id="account-edit-type"
                className="input"
                value={draftType}
                onChange={(event) => setDraftType(event.target.value)}
              >
                {ACCOUNT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 pb-2.5 text-sm text-gray-300">
              <input
                type="checkbox"
                id="account-edit-budget"
                checked={draftBudget}
                onChange={(event) => setDraftBudget(event.target.checked)}
              />
              Budżetowe
            </label>
          </div>
          <div hidden={draftType === "cash"}>
            <div>
              <label
                htmlFor="account-edit-iban"
                className="mb-1 block text-xs text-gray-400"
              >
                IBAN / NRB
              </label>
              <input
                id="account-edit-iban"
                className="input"
                value={draftIban}
                onChange={(event) => setDraftIban(event.target.value)}
              />
              <p className="mt-1 text-xs text-gray-500">
                Wyczyść pole i zapisz, aby usunąć numer rachunku.
              </p>
            </div>
            <details className="border-t border-gray-800 pt-3">
              <summary className="cursor-pointer text-sm text-gray-400">
                Pozostałe dane bankowe
              </summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-gray-400">
                  Bank / instytucja
                  <input
                    className="input mt-1"
                    value={draftBankName}
                    onChange={(event) => setDraftBankName(event.target.value)}
                  />
                </label>
                <label className="text-xs text-gray-400">
                  Właściciel rachunku
                  <input
                    className="input mt-1"
                    value={draftHolder}
                    onChange={(event) => setDraftHolder(event.target.value)}
                  />
                </label>
                <label className="text-xs text-gray-400">
                  BIC / SWIFT
                  <input
                    className="input mt-1"
                    value={draftBic}
                    onChange={(event) => setDraftBic(event.target.value)}
                  />
                </label>
                <label className="text-xs text-gray-400">
                  Notatka
                  <textarea
                    className="input mt-1"
                    value={draftNotes}
                    onChange={(event) => setDraftNotes(event.target.value)}
                  />
                </label>
              </div>
            </details>
          </div>
        </div>
      ) : null}
      {(updateErrorForRow ?? deleteErrorForRow) ? (
        <p className="mt-2 w-full text-xs text-red-400">
          {updateErrorForRow ?? deleteErrorForRow}
        </p>
      ) : null}
    </div>
  );
}
