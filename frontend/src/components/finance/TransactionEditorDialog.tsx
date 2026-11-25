import { useDeferredValue, useId, useState } from "react";
import type { AxiosError } from "axios";
import {
  type Transaction,
  type TransactionEditorResponse,
  type TransactionLedgerInput,
  useTransactionEditor,
  useUpdateTransactionEditor,
} from "../../api/finance";
import type {
  TransactionAnnotations,
  TransactionAnnotationsInput,
} from "../../api/transactionAnnotations";
import { useAnnotationTags } from "../../api/transactionAnnotations";
import { useProjects } from "../../api/work";
import { useIsMutating } from "@tanstack/react-query";
import { formatPLN } from "../../lib/format";
import { Dialog } from "../Dialog";
import { QueryFeedback } from "../QueryFeedback";
import { TransactionCategorizationDialog } from "./TransactionCategorizationDialog";
import { TransactionForm } from "./TransactionForm";

function errorDetail(error: unknown) {
  const detail = (error as AxiosError<{ detail?: unknown }>).response?.data
    ?.detail;
  return typeof detail === "string"
    ? detail
    : "Nie udało się zapisać zmian. Wprowadzone wartości zachowano.";
}

function categoryPostingCount(transaction: Transaction) {
  return transaction.postings.filter((posting) => posting.category_id).length;
}

function annotationInput(
  annotations: TransactionAnnotations | null | undefined,
): TransactionAnnotationsInput | undefined {
  if (!annotations) return undefined;
  return {
    display_description: annotations.display_description,
    note: annotations.note,
    tags: annotations.tags.map((tag) => tag.name),
    project_id: annotations.project_id,
    expected_version: annotations.version,
    expected_context_snapshot: annotations.context_snapshot,
  };
}

function EditorForm({
  data,
  onClose,
}: {
  data: TransactionEditorResponse;
  onClose: () => void;
}) {
  const [snapshot] = useState(data);
  const {
    transaction,
    ledger_editable: ledgerEditable,
    ledger_lock_reason: lock,
  } = snapshot;
  const cleanTag = (value: string) =>
    value.normalize("NFC").trim().replace(/\s+/gu, " ");
  const tagKey = (value: string) => cleanTag(value).toLocaleLowerCase("pl");
  const [label, setLabel] = useState(
    transaction.annotations?.display_description ?? "",
  );
  const [note, setNote] = useState(transaction.annotations?.note ?? "");
  const [tags, setTags] = useState(
    () => transaction.annotations?.tags.map((tag) => tag.name) ?? [],
  );
  const [tagInput, setTagInput] = useState("");
  const [project, setProject] = useState(
    transaction.annotations?.project_id ?? "",
  );
  const suggestions = useAnnotationTags(useDeferredValue(tagInput));
  const projectId = useId();
  const projects = useProjects();
  const [failure, setFailure] = useState<string | null>(null);
  const [splitWorkflow, setSplitWorkflow] = useState(false);
  const update = useUpdateTransactionEditor();
  const hasSplitCategories = categoryPostingCount(transaction) > 1;
  const supportsSharedLedgerForm =
    ledgerEditable &&
    !hasSplitCategories &&
    ["expense", "income", "transfer"].includes(transaction.type) &&
    transaction.postings.length === 2 &&
    transaction.postings.every(
      (posting) =>
        posting.source_currency === "PLN" ||
        posting.fx_rate_source === "manual",
    );

  if (splitWorkflow) {
    return (
      <TransactionCategorizationDialog id={transaction.id} onClose={onClose} />
    );
  }

  function addTag(value: string) {
    const name = cleanTag(value);
    if (name && !tags.some((tag) => tagKey(tag) === tagKey(name)))
      setTags([...tags, name]);
    setTagInput("");
  }

  function submit(ledger?: TransactionLedgerInput, ledgerChanged = false) {
    if (update.isPending) return;
    const annotations = transaction.annotations;
    const nextAnnotations = annotationInput(annotations);
    if (annotations && nextAnnotations) {
      nextAnnotations.display_description = label.trim() || null;
      nextAnnotations.note = note.trim() || null;
      const pending = cleanTag(tagInput);
      const finalTags =
        pending && !tags.some((tag) => tagKey(tag) === tagKey(pending))
          ? [...tags, pending]
          : tags;
      if (
        finalTags.length > annotations.limits.tags ||
        finalTags.some((tag) => tag.length > annotations.limits.tag_name)
      ) {
        setFailure("Sprawdź liczbę i długość tagów.");
        return;
      }
      nextAnnotations.tags = finalTags;
      nextAnnotations.project_id = project || null;
    }
    const annotationsChanged =
      JSON.stringify(nextAnnotations) !==
      JSON.stringify(annotationInput(annotations));
    if (!ledgerChanged && !annotationsChanged) {
      onClose();
      return;
    }
    update.mutate(
      {
        id: transaction.id,
        expected_updated_at: transaction.updated_at ?? "",
        ...(ledgerChanged && ledger && supportsSharedLedgerForm
          ? {
              ledger,
              expected_date_version: transaction.date_metadata?.version ?? 0,
            }
          : {}),
        ...(annotationsChanged && nextAnnotations
          ? { annotations: nextAnnotations }
          : {}),
      },
      {
        onSuccess: onClose,
        onError: (error) => setFailure(errorDetail(error)),
      },
    );
  }

  return (
    <div className="mt-4 space-y-4">
      {lock ? <p role="status">{lock}</p> : null}
      {transaction.type === "expense" ? (
        <section className="rounded-sm border border-gray-700 p-3">
          <h3 className="font-medium">Podział kategorii</h3>
          {hasSplitCategories ? (
            <p className="mt-1 text-sm text-gray-400">
              Ten zapis ma kilka kategorii. Nie zostanie uproszczony ani
              nadpisany podczas zapisu tego formularza.
            </p>
          ) : (
            <p className="mt-1 text-sm text-gray-400">
              Kategorię lub podział zmienisz w osobnym, sprawdzanym przepływie.
            </p>
          )}
          <button
            type="button"
            className="btn-secondary mt-3"
            onClick={() => setSplitWorkflow(true)}
          >
            Edytuj podział kategorii
          </button>
          <p className="mt-2 text-xs text-gray-400">
            Otwiera osobny, sprawdzany przepływ; najpierw zamyka ten edytor.
          </p>
        </section>
      ) : null}
      {supportsSharedLedgerForm ? (
        <TransactionForm
          initialLedger={transaction}
          editBusy={update.isPending}
          onLedgerSubmit={(ledger, changed) => submit(ledger, changed)}
        />
      ) : (
        <fieldset disabled className="space-y-3">
          <label className="block">
            Opis księgowy
            <input
              className="input mt-1"
              value={transaction.description}
              readOnly
            />
          </label>
          <div
            aria-label="Zapisy księgowe"
            className="space-y-1 text-sm text-gray-400"
          >
            {transaction.postings.map((posting) => (
              <p key={posting.id}>
                {posting.account_id ? `Konto: ${posting.account_id}` : null}
                {posting.category_id
                  ? `Kategoria: ${posting.category_id}`
                  : null}
                {" · "}
                {formatPLN(posting.source_amount)} {posting.source_currency}
              </p>
            ))}
          </div>
        </fieldset>
      )}
      {transaction.annotations ? (
        <fieldset disabled={update.isPending} className="space-y-3">
          <p className="break-words text-sm">
            {transaction.annotations.original_description}
          </p>
          <label className="block">
            Własny opis
            <input
              className="input mt-1"
              value={label}
              maxLength={transaction.annotations.limits.display_description}
              onChange={(event) => setLabel(event.target.value)}
            />
          </label>
          <label className="block">
            Notatka
            <textarea
              className="input mt-1"
              value={note}
              maxLength={transaction.annotations.limits.note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <ul aria-label="Wybrane tagi" className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <li key={tagKey(tag)}>
                {tag}{" "}
                <button
                  type="button"
                  aria-label={`Usuń tag ${tag}`}
                  onClick={() => setTags(tags.filter((item) => item !== tag))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <label className="block">
            Nowy tag
            <input
              className="input mt-1"
              value={tagInput}
              maxLength={transaction.annotations.limits.tag_name}
              onChange={(event) => setTagInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addTag(tagInput);
                }
              }}
            />
          </label>
          <button
            className="btn-secondary"
            type="button"
            disabled={!tagInput.trim()}
            onClick={() => addTag(tagInput)}
          >
            Dodaj tag
          </button>
          <div className="flex flex-wrap gap-2">
            {(suggestions.data ?? [])
              .filter(
                ({ name }) => !tags.some((tag) => tagKey(tag) === tagKey(name)),
              )
              .map(({ id, name }) => (
                <button
                  className="btn-secondary"
                  key={id}
                  type="button"
                  aria-label={`Dodaj tag ${name}`}
                  onClick={() => addTag(name)}
                >
                  {name}
                </button>
              ))}
          </div>
          <div>
            <label htmlFor={projectId}>Projekt</label>
            <select
              id={projectId}
              className="input mt-1"
              value={project}
              onChange={(event) => setProject(event.target.value)}
            >
              <option value="">Bez projektu</option>
              {project &&
                !(projects.data ?? []).some(({ id }) => id === project) && (
                  <option value={project}>
                    {transaction.annotations.project_name ?? "Wybrany projekt"}
                  </option>
                )}
              {Array.isArray(projects.data) &&
                projects.data.map(({ id, name }) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
            </select>
          </div>
        </fieldset>
      ) : null}
      {failure ? <p role="alert">{failure}</p> : null}
      {!supportsSharedLedgerForm ? (
        <div className="flex justify-end gap-3">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
            disabled={update.isPending}
          >
            Anuluj
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={update.isPending}
            onClick={() => submit()}
          >
            {update.isPending ? "Zapisywanie…" : "Zapisz zmiany"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function TransactionEditorDialog({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const query = useTransactionEditor(id);
  const opening = !query.isFetchedAfterMount && query.isFetching;
  const saving =
    useIsMutating({ mutationKey: ["finance", "transaction-editor"] }) > 0;
  return (
    <Dialog
      label="Edytuj transakcję"
      onClose={onClose}
      busy={saving}
      panelClassName="card w-full max-w-2xl"
    >
      <h2 className="text-lg font-semibold">Edytuj transakcję</h2>
      <QueryFeedback
        loading={query.isLoading || opening}
        error={query.isError}
        onRetry={query.refetch}
        errorMessage="Nie udało się pobrać danych do edycji."
      >
        {!opening && query.data ? (
          <EditorForm data={query.data} onClose={onClose} />
        ) : null}
      </QueryFeedback>
    </Dialog>
  );
}
