import { useRef, useState } from "react";
import {
  useSuggestionSettings,
  useSuggestionUsage,
  useChangeSuggestionSettings,
} from "../../api/categoryProposals";
import type {
  SuggestionSettingsData,
  SuggestionSettingsInput,
} from "../../api/categoryProposals";
import { QueryFeedback } from "../QueryFeedback";
import { useAuthStore } from "../../stores/authStore";
import { ruleError } from "../../api/ruleErrors";

export function SuggestionSettings() {
  const query = useSuggestionSettings();
  const usage = useSuggestionUsage();
  const session = useAuthStore((s) => s.sessionVersion);
  return (
    <section aria-label="Propozycje AI" className="card space-y-4">
      <h2 className="text-lg font-semibold">
        Propozycje AI — zawsze do Twojej decyzji
      </h2>
      <QueryFeedback
        loading={query.isLoading}
        error={query.isError}
        errorMessage="Nie udało się pobrać zgody AI."
        onRetry={query.refetch}
        children={null}
      />
      {query.data ? (
        <ConsentForm
          key={session}
          snapshot={query.data}
          refresh={async () => {
            const result = await query.refetch();
            return result.data;
          }}
        />
      ) : null}
      {usage.isError ? (
        <p role="alert">Nie udało się pobrać zużycia AI.</p>
      ) : usage.data ? (
        <div className="border-t border-gray-800 pt-3 text-sm text-gray-400">
          <p>
            Limit {usage.data.limit} potencjalnych wywołań / dobę UTC.
            Pozostało: {usage.data.remaining_slots}.
          </p>
          <p>
            Nieznane wywołania: {usage.data.unknown}. Zarezerwowane:{" "}
            {usage.data.held}.
          </p>
          <p>
            Znane tokeny: wejście {usage.data.known_input_tokens ?? "nieznane"},
            wyjście {usage.data.known_output_tokens ?? "nieznane"}.
          </p>
          <p>
            Koszt PLN nie jest wyliczany bez cennika. Brak danych nie oznacza
            bezpłatnej analizy.
          </p>
        </div>
      ) : null}
    </section>
  );
}

function ConsentForm({
  snapshot,
  refresh,
}: {
  snapshot: SuggestionSettingsData;
  refresh: () => Promise<SuggestionSettingsData | undefined>;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const [scope, setScope] = useState(snapshot);
  const [version, setVersion] = useState(snapshot.version);
  const [enabled, setEnabled] = useState(snapshot.enabled);
  const [exportConsent, setExportConsent] = useState(false);
  const [future, setFuture] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [stale, setStale] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const intent = useRef<SuggestionSettingsInput | null>(null);
  const busyRef = useRef(false);
  const command = useChangeSuggestionSettings();
  const scopeChanged =
    snapshot.server_epoch !== scope.server_epoch ||
    snapshot.configuration_fingerprint !== scope.configuration_fingerprint;
  const invalid = stale || scopeChanged;
  function change() {
    intent.current = null;
    setMessage(null);
    setExportConsent(false);
    setFuture(false);
  }
  async function save() {
    if (busyRef.current || !active) return;
    const input = intent.current ?? {
      session,
      key: crypto.randomUUID(),
      expected_version: version,
      enabled,
      ...(enabled
        ? {
            expected_server_epoch: scope.server_epoch,
            expected_configuration_fingerprint: scope.configuration_fingerprint,
            confirm_future_only: true as const,
            confirm_data_export: true as const,
          }
        : {}),
    };
    intent.current = input;
    busyRef.current = true;
    try {
      const result = await command.mutateAsync(input);
      if (session !== useAuthStore.getState().sessionVersion) return;
      setVersion(result.version);
      setScope(result);
      setEnabled(result.enabled);
      setExportConsent(false);
      setFuture(false);
      setUncertain(false);
      setStale(false);
      intent.current = null;
      setMessage("Zgoda AI zapisana.");
    } catch (error) {
      if (session === useAuthStore.getState().sessionVersion) {
        const f = ruleError(error);
        setMessage(f.message);
        setUncertain(f.uncertain);
        setStale(f.stale);
      }
    } finally {
      busyRef.current = false;
    }
  }
  async function reload() {
    const result = await refresh();
    if (result && session === useAuthStore.getState().sessionVersion) {
      setScope(result);
      setVersion(result.version);
      setEnabled(result.enabled);
      setStale(false);
      setUncertain(false);
      change();
    }
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-400">{scope.privacy_text}</p>
      <p className="text-sm text-gray-400">
        Limit opisu: {scope.max_description_chars} znaków; katalog do{" "}
        {scope.max_categories} kategorii. Nie przeglądamy historii.
      </p>
      {!snapshot.available ? (
        <p role="status">
          Generowanie AI nie jest dostępne. Wymaga osobnej aktywacji serwera.
        </p>
      ) : snapshot.effective_enabled ? (
        <p role="status">
          Generowanie propozycji dla nowych wydatków jest włączone.
        </p>
      ) : (
        <p role="status">
          Generowanie propozycji jest wyłączone lub wymaga ponownej zgody.
        </p>
      )}
      {!active ? (
        <p role="alert">Sesja zmieniła się. Wczytaj aktualne dane.</p>
      ) : null}
      <fieldset
        disabled={!active || command.isPending || uncertain || invalid}
        className="space-y-3"
      >
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={enabled}
            disabled={!snapshot.available && !enabled}
            onChange={(e) => {
              change();
              setEnabled(e.target.checked);
            }}
          />
          Włącz propozycje AI dla nowych wydatków
        </label>
        {enabled ? (
          <>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={exportConsent}
                onChange={(e) => setExportConsent(e.target.checked)}
              />
              Zgadzam się wysyłać opis i katalog kategorii do AI w pokazanym
              zakresie
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={future}
                onChange={(e) => setFuture(e.target.checked)}
              />
              Tylko nowe wydatki; każdą propozycję zatwierdzę osobno po
              przeglądzie
            </label>
          </>
        ) : null}
      </fieldset>
      {message ? (
        <p role="status" className="text-sm">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={
            !active ||
            command.isPending ||
            (!uncertain &&
              (invalid ||
                (enabled &&
                  (!snapshot.available || !exportConsent || !future))))
          }
          onClick={() => void save()}
        >
          {uncertain ? "Ponów zapis zgody AI" : "Zapisz zgodę AI"}
        </button>
        {invalid ? (
          <button
            type="button"
            className="btn-secondary"
            disabled={!active || command.isPending}
            onClick={() => void reload()}
          >
            Wczytaj aktualne ustawienia
          </button>
        ) : null}
      </div>
    </div>
  );
}
