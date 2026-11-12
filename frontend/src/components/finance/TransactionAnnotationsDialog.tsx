import {
  useDeferredValue,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";
import type { AxiosError } from "axios";
import {
  useAnnotationTags,
  useTransactionAnnotations,
  useUpdateTransactionAnnotations,
  type TransactionAnnotations,
  type TransactionAnnotationsInput,
} from "../../api/transactionAnnotations";
import { useProjects } from "../../api/work";
import { useAuthStore } from "../../stores/authStore";
import { Dialog } from "../Dialog";
import { QueryFeedback } from "../QueryFeedback";

const cleanTag = (value: string) =>
  value.normalize("NFC").trim().replace(/\s+/gu, " ");
const tagKey = (value: string) => cleanTag(value).toLocaleLowerCase("pl");

export function TransactionAnnotationsDialog({
  transactionId,
  onClose,
}: {
  transactionId: string;
  onClose: () => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((state) => state.sessionVersion) === session;
  const query = useTransactionAnnotations(transactionId);
  const mutation = useUpdateTransactionAnnotations();
  return (
    <Dialog
      label="Opis i oznaczenia"
      onClose={onClose}
      panelClassName="card max-w-xl w-full"
      busy={mutation.isPending}
    >
      <h2 className="text-lg font-semibold">Opis i oznaczenia</h2>
      {!active ? (
        <p role="alert">
          Sesja zmieniła się. Zamknij okno i wczytaj aktualne dane.
        </p>
      ) : (
        <QueryFeedback
          loading={query.isLoading}
          error={query.isError}
          onRetry={query.refetch}
          errorMessage="Nie udało się pobrać oznaczeń transakcji."
        >
          {query.data ? (
            <AnnotationForm
              transactionId={transactionId}
              initial={query.data}
              session={session}
              onClose={onClose}
              mutation={mutation}
            />
          ) : null}
        </QueryFeedback>
      )}
    </Dialog>
  );
}

function AnnotationForm({
  transactionId,
  initial,
  session,
  onClose,
  mutation,
}: {
  transactionId: string;
  initial: TransactionAnnotations;
  session: number;
  onClose: () => void;
  mutation: ReturnType<typeof useUpdateTransactionAnnotations>;
}) {
  // A refetch must never replace a draft or silently accept a newer version.
  const [snapshot] = useState(initial);
  const [title, setTitle] = useState(snapshot.display_description ?? "");
  const [note, setNote] = useState(snapshot.note ?? "");
  const [tags, setTags] = useState(() => snapshot.tags.map((tag) => tag.name));
  const [tagInput, setTagInput] = useState("");
  const [project, setProject] = useState(snapshot.project_id ?? "");
  const projectControlId = useId();
  const [failure, setFailure] = useState<string | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const projects = useProjects();
  const suggestions = useAnnotationTags(useDeferredValue(tagInput));
  const intent = useRef<{ serialized: string; key: string } | null>(null);
  const active = useAuthStore((state) => state.sessionVersion) === session;
  function addTag(value: string) {
    const name = cleanTag(value);
    if (!name || name.length > snapshot.limits.tag_name) {
      setFailure("Wpisz tag w dozwolonej długości.");
      return;
    }
    if (!tags.some((tag) => tagKey(tag) === tagKey(name))) {
      if (tags.length >= snapshot.limits.tags) {
        setFailure("Osiągnięto limit tagów.");
        return;
      }
      setTags((previous) => [...previous, name]);
    }
    setTagInput("");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!active || needsRefresh || mutation.isPending) return;
    const finalTags = [...tags];
    const pending = cleanTag(tagInput);
    if (pending && !tags.some((tag) => tagKey(tag) === tagKey(pending)))
      finalTags.push(pending);
    if (
      finalTags.length > snapshot.limits.tags ||
      finalTags.some((tag) => !tag || tag.length > snapshot.limits.tag_name)
    ) {
      setFailure("Sprawdź liczbę i długość tagów.");
      return;
    }
    const body: TransactionAnnotationsInput = {
      display_description: title.trim() || null,
      note: note.trim() || null,
      tags: finalTags,
      project_id: project || null,
      expected_version: snapshot.version,
      expected_context_snapshot: snapshot.context_snapshot,
    };
    const serialized = JSON.stringify(body);
    if (intent.current?.serialized !== serialized)
      intent.current = { serialized, key: crypto.randomUUID() };
    setFailure(null);
    mutation.mutate(
      { id: transactionId, key: intent.current.key, ...body },
      {
        onSuccess: () => {
          if (useAuthStore.getState().sessionVersion === session) onClose();
        },
        onError: (error) => {
          if (useAuthStore.getState().sessionVersion !== session) return;
          const response = (error as AxiosError<{ detail?: unknown }>).response;
          const detail = response?.data?.detail;
          setFailure(
            typeof detail === "string"
              ? detail
              : "Nie udało się zapisać oznaczeń. Sprawdź dane; wprowadzone wartości zachowano.",
          );
          setNeedsRefresh(response?.status === 409);
        },
      },
    );
  }
  const knownProjects = projects.data ?? [];
  return (
    <form onSubmit={submit} className="mt-4 space-y-4">
      <p className="text-sm text-gray-400">
        Zmiany nie wpływają na kwotę, konto ani daty transakcji.
      </p>
      <div className="rounded-sm border border-gray-700 bg-gray-900/50 p-3">
        <h3 className="text-xs text-gray-400">Oryginalny opis — bez zmian</h3>
        <p className="mt-1 whitespace-pre-wrap text-sm [overflow-wrap:anywhere]">
          {snapshot.original_description}
        </p>
      </div>
      <fieldset disabled={mutation.isPending || !active} className="space-y-4">
        <label className="block">
          Własny opis
          <input
            className="input mt-1"
            value={title}
            maxLength={snapshot.limits.display_description}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <p className="text-xs text-gray-400">
          Puste pole przywraca oryginalny opis.
        </p>
        <label className="block">
          Notatka
          <textarea
            className="input mt-1 min-h-24"
            rows={3}
            value={note}
            maxLength={snapshot.limits.note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <div>
          <p className="mb-2 text-sm">Tagi</p>
          <ul className="flex flex-wrap gap-2" aria-label="Wybrane tagi">
            {tags.map((tag) => (
              <li
                key={tagKey(tag)}
                className="flex max-w-full items-center gap-2 rounded-sm border border-gray-700 px-2 py-1 text-sm"
              >
                <span className="[overflow-wrap:anywhere]">{tag}</span>
                <button
                  type="button"
                  aria-label={`Usuń tag ${tag}`}
                  onClick={() =>
                    setTags((previous) =>
                      previous.filter((value) => value !== tag),
                    )
                  }
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <label className="mt-2 block">
            Nowy tag
            <input
              className="input mt-1"
              value={tagInput}
              maxLength={snapshot.limits.tag_name}
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
            type="button"
            className="btn-secondary mt-2"
            onClick={() => addTag(tagInput)}
            disabled={!tagInput.trim()}
          >
            Dodaj tag
          </button>
          <p className="mt-1 text-xs text-gray-400">
            Wpisz własny tag lub wybierz istniejący. Nowe tagi powstaną dopiero
            po zapisaniu.
          </p>
          {suggestions.isError ? (
            <p className="text-xs text-gray-400">
              Podpowiedzi są niedostępne. Możesz wpisać tag samodzielnie.
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            {(suggestions.data ?? [])
              .filter(
                (tag) =>
                  !tags.some(
                    (selected) => tagKey(selected) === tagKey(tag.name),
                  ),
              )
              .map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  className="btn-secondary max-w-full text-sm [overflow-wrap:anywhere]"
                  aria-label={`Dodaj tag ${tag.name}`}
                  onClick={() => addTag(tag.name)}
                >
                  {tag.name}
                </button>
              ))}
          </div>
        </div>
        <div>
          <label htmlFor={projectControlId} className="block">
            Projekt
          </label>
          <select
            id={projectControlId}
            className="input mt-1"
            value={project}
            onChange={(event) => setProject(event.target.value)}
          >
            <option value="">Bez projektu</option>
            {project && !knownProjects.some((item) => item.id === project) ? (
              <option value={project}>
                {snapshot.project_name ?? "Bieżący projekt"}
              </option>
            ) : null}
            {knownProjects.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        {projects.isError ? (
          <p className="text-xs text-gray-400">
            Lista projektów jest niedostępna. Dotychczasowe powiązanie pozostaje
            zachowane.
          </p>
        ) : null}
      </fieldset>
      {failure ? (
        <p
          role="alert"
          className="text-sm text-red-400 [overflow-wrap:anywhere]"
        >
          {failure}
        </p>
      ) : null}
      {needsRefresh ? (
        <p className="text-sm text-gray-300">
          Zachowano wpisane wartości. Zamknij okno i odśwież transakcję przed
          kolejnym zapisem.
        </p>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          className="btn-secondary"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          Anuluj
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={mutation.isPending || needsRefresh || !active}
        >
          {mutation.isPending ? "Zapisywanie…" : "Zapisz oznaczenia"}
        </button>
      </div>
    </form>
  );
}
