import { useState } from "react";
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
    onStartEdit();
  }

  function save() {
    updateMutation.mutate(
      {
        id: account.id,
        name: draftName,
        type: draftType,
        is_budget_account: draftBudget,
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

  return (
    <div
      className={`rounded-lg border border-gray-800 bg-gray-800/40 p-3 ${
        account.is_active ? "" : "opacity-60"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-white">
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
        </div>
        <div className="flex shrink-0 gap-2">
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
