import { useId, type FormEvent } from "react";
import { isAxiosError } from "axios";
import { useAIBenchmark, type AISettingsView } from "../../api/aiSettings";

const statuses: Record<string, string> = {
  ok: "Odpowiedź odebrana",
  partial: "Wynik częściowy",
  failed: "Brak poprawnie odczytanych odpowiedzi",
  not_configured: "Brak klucza lub modelu",
  rejected_key: "OpenAI odrzucił klucz",
  model_unavailable: "Model niedostępny",
  rate_limited: "OpenAI ograniczył wywołania",
  timeout: "Przekroczono czas oczekiwania",
  unusable_response: "Nie udało się odczytać odpowiedzi",
  provider_error: "Błąd połączenia z OpenAI",
};

const cases: Record<string, string> = {
  classify_task: "Rozpoznanie zadania",
  missing_facts: "Rozpoznanie braku danych",
  source_reference: "Wybór właściwego źródła",
};
const labels = ["A", "B"] as const;

export function AIBenchmark({ settings }: { settings?: AISettingsView }) {
  const id = useId();
  const benchmark = useAIBenchmark();
  const error = isAxiosError(benchmark.error)
    ? benchmark.error.response?.status
    : undefined;

  function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (benchmark.isPending) return;
    const data = new FormData(event.currentTarget);
    const variant = (suffix: string) => ({
      model: String(data.get(`model${suffix}`) ?? "").trim(),
      instructions:
        String(data.get(`instructions${suffix}`) ?? "").trim() || null,
    });
    benchmark.mutate([variant("A"), variant("B")]);
  }

  return (
    <section className="card space-y-3" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="text-lg font-semibold">
        Porównanie modeli i instrukcji
      </h2>
      <p className="text-sm text-gray-400">
        Trzy syntetyczne zadania na wariant, do sześciu wywołań OpenAI. Możesz
        porównać ten sam model z różnymi instrukcjami. Nie wpisuj danych
        osobowych ani sekretów: instrukcje zostaną wysłane do OpenAI. Test
        niczego nie zapisuje w ustawieniach.
      </p>
      <form onSubmit={run} className="space-y-3">
        <datalist id={`${id}-models`}>
          {settings?.server_models.map((model) => (
            <option key={model} value={model} />
          ))}
        </datalist>
        <div className="grid gap-3 md:grid-cols-2">
          {labels.map((label) => (
            <fieldset
              key={label}
              disabled={benchmark.isPending}
              className="min-w-0 space-y-2"
            >
              <legend className="font-medium">Wariant {label}</legend>
              <label className="grid gap-1 text-sm">
                Model {label}
                <input
                  name={`model${label}`}
                  list={`${id}-models`}
                  required
                  maxLength={128}
                  pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}"
                  className="input-field"
                  defaultValue={settings?.active_model ?? ""}
                />
              </label>
              <label className="grid gap-1 text-sm">
                Instrukcje {label} (opcjonalne)
                <textarea
                  name={`instructions${label}`}
                  maxLength={4000}
                  rows={3}
                  className="input-field"
                />
              </label>
            </fieldset>
          ))}
        </div>
        <button
          type="submit"
          className="btn-secondary"
          disabled={benchmark.isPending}
        >
          Uruchom porównanie OpenAI
        </button>
      </form>
      {benchmark.isPending && <p role="status">Porównuję warianty…</p>}
      {benchmark.isError && (
        <p role="alert">
          {error === 429
            ? "Limit uruchomień został wykorzystany. Spróbuj później."
            : error === 422
              ? "Sprawdź identyfikatory modeli i instrukcje. Własny model wymaga własnego klucza."
              : "Nie udało się uruchomić porównania."}
        </p>
      )}
      {benchmark.data && (
        <div className="space-y-2" aria-live="polite">
          <p className="text-sm text-gray-400">
            Zestaw: {benchmark.data.suite_version}. Wynik dotyczy tylko tych
            przykładów.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {benchmark.data.variants.map((variant, index) => (
              <div
                key={index}
                className="min-w-0 space-y-2 break-words rounded-lg border border-gray-800 p-3"
              >
                <h3 className="font-semibold">
                  Wariant {labels[index]}: {variant.model}
                </h3>
                <p className="text-sm">{statuses[variant.status]}</p>
                <ul className="space-y-2 text-sm">
                  {variant.cases.map((item) => (
                    <li key={item.case_id}>
                      <p>
                        {cases[item.case_id] ?? item.case_id}:{" "}
                        {item.matches_expected === null
                          ? (statuses[item.status] ?? "Błąd")
                          : item.matches_expected
                            ? "Zgodna z oczekiwaniem"
                            : "Niezgodna z oczekiwaniem"}
                      </p>
                      <p className="text-gray-400">
                        {item.duration_ms} ms · Tokeny wejścia:{" "}
                        {item.input_tokens ?? "—"} · Tokeny wyjścia:{" "}
                        {item.output_tokens ?? "—"}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
