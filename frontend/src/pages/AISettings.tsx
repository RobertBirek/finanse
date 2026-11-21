import { useRef, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  aiSettingsKey,
  aiSettingsPath,
  purposeParams,
  useAIPrompts,
  useAISettingChange,
  useAISettings,
  useAIUsage,
  useProbeAI,
  type AISettingsView,
  type AIPurpose,
  type UsageDays,
} from "../api/aiSettings";
import { QueryFeedback } from "../components/QueryFeedback";
import { PageHeader } from "../components/PageHeader";
import { AIBenchmark } from "../components/advisor/AIBenchmark";
import api from "../lib/api";

const statusLabels: Record<string, string> = {
  ok: "Połączenie działa. Model obsługuje wywołania narzędzi.",
  not_configured: "Najpierw skonfiguruj klucz i model.",
  rejected_key: "OpenAI odrzucił klucz. Sprawdź klucz i uprawnienia projektu.",
  model_unavailable:
    "Model jest niedostępny lub nie obsługuje wymaganych funkcji.",
  rate_limited: "OpenAI ograniczył wywołania. Sprawdź limit lub rozliczenia.",
  timeout: "OpenAI nie odpowiedział na czas.",
  unusable_response: "Model nie wykonał oczekiwanego wywołania narzędzia.",
  provider_error: "Nie udało się połączyć z OpenAI.",
};

interface PurposeSettings {
  settings: AISettingsView;
  purpose: AIPurpose;
}

function CredentialForm({ settings, purpose }: PurposeSettings) {
  const client = useQueryClient();
  const field = useRef<HTMLInputElement>(null);
  const remove = useAISettingChange(purpose);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(
    null,
  );

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!field.current || saving || remove.isPending) return;
    const key = field.current.value.trim();
    if (!key) return;
    field.current.value = "";
    setNotice(null);
    setSaving(true);
    try {
      await api.put(
        `${aiSettingsPath}/credential`,
        { api_key: key },
        purposeParams(purpose),
      );
      await client.invalidateQueries({ queryKey: [...aiSettingsKey, purpose] });
      setNotice({ error: false, text: "Zapisano własny klucz." });
    } catch {
      setNotice({
        error: true,
        text: "Nie zapisano klucza. Wprowadź go ponownie.",
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card space-y-3" aria-labelledby="ai-key-title">
      <h2 className="text-lg font-semibold" id="ai-key-title">
        Klucz API
      </h2>
      <p className="text-sm text-gray-300">
        {settings.credential_source === "custom"
          ? "Zapisano własny klucz. Nie można go ponownie wyświetlić."
          : settings.credential_source === "server"
            ? "Ta funkcja korzysta z klucza serwera."
            : "Nie skonfigurowano klucza OpenAI."}
      </p>
      {settings.custom_key_available ? (
        <form className="space-y-2" onSubmit={save}>
          <label className="block text-sm" htmlFor="ai-api-key">
            Nowy klucz API
          </label>
          <input
            className="input w-full"
            id="ai-api-key"
            type="password"
            ref={field}
            autoComplete="off"
            spellCheck={false}
            required
            maxLength={512}
            disabled={saving || remove.isPending}
          />
          <button className="btn-primary" disabled={saving || remove.isPending}>
            Zapisz klucz
          </button>
        </form>
      ) : (
        <p className="text-sm text-gray-400">
          Serwer nie ma skonfigurowanego szyfrowania własnych kluczy.
        </p>
      )}
      {settings.credential_source === "custom" && (
        <button
          className="btn-secondary"
          type="button"
          disabled={saving || remove.isPending}
          onClick={() => {
            setNotice(null);
            remove.mutate(
              { kind: "removeCredential" },
              {
                onSuccess: () =>
                  setNotice({ error: false, text: "Usunięto własny klucz." }),
                onError: () =>
                  setNotice({
                    error: true,
                    text: "Nie udało się usunąć klucza.",
                  }),
              },
            );
          }}
        >
          Usuń własny klucz i wróć do klucza serwera
        </button>
      )}
      {notice && (
        <p role={notice.error ? "alert" : "status"} className="text-sm">
          {notice.text}
        </p>
      )}
    </section>
  );
}

function Connection({ settings, purpose }: PurposeSettings) {
  const [draft, setDraft] = useState<string | null>(null);
  const update = useAISettingChange(purpose);
  const probe = useProbeAI(purpose);
  const model = draft ?? settings.model ?? "";
  const busy = update.isPending || probe.isPending;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    probe.reset();
    update.mutate(
      { kind: "model", value: model.trim() || null },
      {
        onSuccess: () => setDraft(null),
      },
    );
  }

  return (
    <section className="card space-y-4" aria-labelledby="ai-model-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ai-model-title" className="text-lg font-semibold">
          Połączenie z OpenAI
        </h2>
        <span className="font-mono text-xs text-gray-300">
          OPENAI / RESPONSES
        </span>
      </div>
      <div className="border-l-2 border-advisor-500 pl-3">
        <p className="text-sm text-gray-400">Aktywny model</p>
        <p className="font-mono break-all">
          {settings.active_model ?? "Brak modelu"}
        </p>
      </div>
      <form onSubmit={save} className="space-y-2">
        <label htmlFor="ai-model" className="block text-sm">
          Model {purpose === "advisor" ? "Doradcy" : "OpenAI"}
        </label>
        {settings.credential_source === "custom" ? (
          <>
            <input
              id="ai-model"
              list="ai-server-models"
              className="input w-full"
              value={model}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={
                settings.server_model ?? "Identyfikator modelu OpenAI"
              }
              maxLength={128}
              disabled={busy}
            />
            <datalist id="ai-server-models">
              {settings.server_models.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </>
        ) : (
          <select
            id="ai-model"
            className="input w-full"
            value={model}
            disabled={busy || settings.operational === false}
            onChange={(event) => setDraft(event.target.value)}
          >
            <option value="">Domyślny model serwera</option>
            {settings.server_models.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-primary"
            disabled={busy || model.trim() === (settings.model ?? "")}
          >
            Zapisz model
          </button>
          <button
            className="btn-secondary"
            type="button"
            disabled={busy || settings.operational === false}
            onClick={() => probe.mutate()}
          >
            {probe.isPending ? "Testowanie…" : "Testuj zapisane połączenie"}
          </button>
        </div>
        {update.isError && (
          <p role="alert">Nie zapisano modelu. Sprawdź jego identyfikator.</p>
        )}
        {probe.isError && (
          <p role="alert">
            Nie udało się uruchomić testu. Sprawdź konfigurację i spróbuj
            później.
          </p>
        )}
        {probe.data && (
          <p
            role={probe.data.status === "ok" ? "status" : "alert"}
            className="text-sm"
          >
            {probe.data.status === "ok" && purpose !== "advisor"
              ? "Połączenie działa. Próba odczytu danych syntetycznych zakończyła się poprawnie."
              : (statusLabels[probe.data.status] ??
                statusLabels.provider_error)}
            {probe.data.status === "ok" && ` (${probe.data.duration_ms} ms)`}
          </p>
        )}
        <p className="text-xs text-gray-400">
          Test wysyła tylko syntetyczne polecenie; może zużyć tokeny.
        </p>
      </form>
    </section>
  );
}

function Instructions({
  active,
  purpose,
}: {
  active: string | null;
  purpose: AIPurpose;
}) {
  const history = useAIPrompts(purpose);
  const change = useAISettingChange(purpose);
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? active ?? "";

  function save(next: string | null) {
    change.mutate(
      { kind: "prompt", value: next },
      { onSuccess: () => setDraft(null) },
    );
  }
  return (
    <section className="card space-y-3" aria-labelledby="ai-prompt-title">
      <h2 id="ai-prompt-title" className="text-lg font-semibold">
        Własne instrukcje
      </h2>
      <p className="text-sm text-gray-400">
        Ustaw ton lub sposób odpowiedzi. Te instrukcje nie zmieniają uprawnień
        ani obowiązku potwierdzania zapisów.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save(value.trim() || null);
        }}
        className="space-y-3"
      >
        <label className="block text-sm" htmlFor="ai-prompt">
          Własne instrukcje systemowe
        </label>
        <textarea
          id="ai-prompt"
          className="input w-full font-mono"
          rows={5}
          maxLength={4000}
          value={value}
          onChange={(event) => setDraft(event.target.value)}
          disabled={change.isPending}
        />
        <div className="flex flex-wrap gap-2">
          <button
            className="btn-primary"
            disabled={change.isPending || value.trim() === (active ?? "")}
          >
            Zapisz instrukcje
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={change.isPending || active === null}
            onClick={() => save(null)}
          >
            Przywróć domyślne
          </button>
        </div>
        {change.isError && (
          <p role="alert">Nie udało się zapisać instrukcji.</p>
        )}
      </form>
      <details>
        <summary className="cursor-pointer text-sm">
          Historia wersji (ostatnie 30)
        </summary>
        <QueryFeedback
          loading={history.isLoading}
          error={history.isError}
          errorMessage="Nie udało się pobrać wersji."
          onRetry={history.refetch}
        >
          {!history.data?.length && (
            <p className="text-sm text-gray-400">Brak zapisanych wersji.</p>
          )}
          <ul className="mt-2 space-y-2">
            {history.data?.map((version) => (
              <li
                key={version.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-700 py-2"
              >
                <span className="min-w-0 break-words text-sm">
                  {new Date(version.created_at).toLocaleString("pl-PL")} ·{" "}
                  {version.instructions?.slice(0, 90) ?? "Domyślne"}
                </span>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={change.isPending}
                  onClick={() => setDraft(version.instructions ?? "")}
                >
                  Wczytaj do edytora
                </button>
              </li>
            ))}
          </ul>
        </QueryFeedback>
      </details>
    </section>
  );
}

const periods: UsageDays[] = [7, 30, 90];
const number = new Intl.NumberFormat("pl-PL");
function format(value: number | null) {
  return value === null ? "—" : number.format(value);
}

function Usage({ purpose }: { purpose: AIPurpose }) {
  const [days, setDays] = useState<UsageDays>(30);
  const usage = useAIUsage(days, purpose);
  return (
    <section className="card space-y-3" aria-labelledby="ai-usage-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="ai-usage-title" className="text-lg font-semibold">
          Użycie OpenAI
        </h2>
        <div
          role="group"
          aria-label="Okres użycia"
          className="flex flex-wrap gap-2"
        >
          {periods.map((period) => (
            <button
              key={period}
              type="button"
              className={days === period ? "btn-primary" : "btn-secondary"}
              aria-pressed={days === period}
              onClick={() => setDays(period)}
            >
              {period} dni
            </button>
          ))}
        </div>
      </div>
      <QueryFeedback
        loading={usage.isLoading}
        error={usage.isError}
        errorMessage="Nie udało się pobrać statystyk."
        onRetry={usage.refetch}
      >
        {!usage.data?.length ? (
          <p className="text-sm text-gray-400">
            Brak zarejestrowanych wywołań w tym okresie.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  <th scope="col" className="p-2">
                    Funkcja / model
                  </th>
                  <th scope="col" className="p-2">
                    Wywołania / błędy
                  </th>
                  <th scope="col" className="p-2">
                    Śr. czas
                  </th>
                  <th scope="col" className="p-2">
                    Tokeny wej. / wyj.
                  </th>
                </tr>
              </thead>
              <tbody>
                {usage.data.map((row) => (
                  <tr
                    key={`${row.kind}:${row.model}`}
                    className="border-t border-gray-700"
                  >
                    <th scope="row" className="p-2 font-normal">
                      {row.kind === "test"
                        ? "Test połączenia"
                        : "Użycie funkcji"}
                      <span className="block break-all font-mono text-xs">
                        {row.model}
                      </span>
                    </th>
                    <td className="p-2">
                      {format(row.requests)} / {format(row.errors)}
                    </td>
                    <td className="p-2">
                      {format(row.average_duration_ms)} ms
                    </td>
                    <td className="p-2">
                      {format(row.input_tokens)} / {format(row.output_tokens)}
                      {row.reports_with_tokens < row.requests && (
                        <span className="block text-xs text-gray-400">
                          Raporty tokenów: {row.reports_with_tokens}/
                          {row.requests}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryFeedback>
      <p className="text-xs text-gray-400">
        „—” oznacza brak pomiaru. Te dane nie są fakturą OpenAI.
      </p>
    </section>
  );
}

const purposeLabels: Record<AIPurpose, string> = {
  advisor: "Doradca",
  document_text: "Tekst dokumentów",
  vision: "Analiza zdjęć",
  receipt: "Pozycje paragonów",
  categorization: "Kategoryzacja",
};

const purposes = Object.keys(purposeLabels) as AIPurpose[];

export function AISettings() {
  const [purpose, setPurpose] = useState<AIPurpose>("advisor");
  const query = useAISettings(purpose);
  const data = query.data;
  return (
    <div className="page-workspace">
      <PageHeader
        title="Ustawienia AI"
        description="Każda funkcja ma osobny model, klucz, instrukcje i statystyki."
        context={
          <Link className="underline" to="/settings">
            Ustawienia
          </Link>
        }
      />
      <div
        role="group"
        aria-label="Funkcja AI"
        className="mb-4 flex flex-wrap gap-2"
      >
        {purposes.map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={purpose === item}
            className={purpose === item ? "btn-primary" : "btn-secondary"}
            onClick={() => setPurpose(item)}
          >
            {purposeLabels[item]}
          </button>
        ))}
      </div>
      <QueryFeedback
        loading={query.isLoading}
        error={query.isError}
        errorMessage="Nie udało się pobrać ustawień AI."
        onRetry={query.refetch}
      >
        {data && (
          <div key={purpose} className="workspace-panels">
            {data.operational === false && (
              <p className="workspace-span text-sm text-gray-400">
                Ta funkcja nie ma aktywnej konfiguracji na serwerze. Zapis
                ustawień nie uruchamia przetwarzania.
              </p>
            )}
            {purpose === "categorization" && (
              <p className="workspace-span text-sm text-gray-400">
                Po zmianie ustawień potwierdź ponownie wysyłanie danych w{" "}
                <Link
                  className="underline"
                  to="/settings/finances/categorization"
                >
                  ustawieniach kategoryzacji
                </Link>
                .
              </p>
            )}
            {purpose === "receipt" && (
              <p className="workspace-span text-sm text-gray-400">
                Zdjęcie paragonu trafi do wybranego modelu dopiero po osobnym
                potwierdzeniu odczytu.
              </p>
            )}
            <Connection
              key={data.credential_source}
              settings={data}
              purpose={purpose}
            />
            <CredentialForm settings={data} purpose={purpose} />
            <Instructions active={data.instructions} purpose={purpose} />
            {purpose === "advisor" && <AIBenchmark settings={data} />}
            <div className="workspace-span min-w-0">
              <Usage purpose={purpose} />
            </div>
          </div>
        )}
      </QueryFeedback>
    </div>
  );
}
