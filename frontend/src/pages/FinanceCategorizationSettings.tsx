import { useState } from "react";
import {
  type CategorizationRule,
  type RuleSettings,
  useCategorizationRules,
  useCategorizationSettings,
  useRuleCommand,
} from "../api/categorizationRules";
import { useCategories } from "../api/finance";
import { CategoryPicker } from "../components/finance/CategoryPicker";
import { RuleEditor } from "../components/finance/RuleEditor";
import { ruleError } from "../api/ruleErrors";
import { QueryFeedback } from "../components/QueryFeedback";
import { useAuthStore } from "../stores/authStore";
import api from "../lib/api";
import { categoryPath } from "../lib/categories";
import { SuggestionSettings } from "../components/finance/SuggestionSettings";

function MarkerSettings({ snapshot }: { snapshot: RuleSettings }) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const categories = useCategories();
  const command = useRuleCommand();
  const [marker, setMarker] = useState(
    snapshot.uncategorized_category_id ?? "",
  );
  const [enabled, setEnabled] = useState(snapshot.rules_enabled);
  const [version, setVersion] = useState(snapshot.version);
  const [confirmed, setConfirmed] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [failure, setFailure] = useState<ReturnType<typeof ruleError> | null>(
    null,
  );
  const [saved, setSaved] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  function change() {
    setConfirmed(false);
    setKey(crypto.randomUUID());
    setFailure(null);
    setSaved(false);
  }
  async function save() {
    try {
      const value = (await command.mutateAsync({
        session,
        method: "patch",
        path: "/settings",
        key,
        body: {
          expected_version: version,
          uncategorized_category_id: marker || null,
          rules_enabled: enabled,
          confirm_future_only: true,
        },
      })) as RuleSettings;
      if (useAuthStore.getState().sessionVersion !== session) return;
      setVersion(value.version);
      setSaved(true);
      setConfirmed(false);
      setFailure(null);
      setUncertain(false);
      setKey(crypto.randomUUID());
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session) {
        const f = ruleError(error);
        setFailure(f);
        setUncertain(f.uncertain);
      }
    }
  }
  async function refresh() {
    try {
      const { data } = await api.get<RuleSettings>(
        "/finance/categorization/settings",
      );
      if (useAuthStore.getState().sessionVersion !== session) return;
      setVersion(data.version);
      setConfirmed(false);
      setFailure(null);
      setUncertain(false);
      setKey(crypto.randomUUID());
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session)
        setFailure(ruleError(error));
    }
  }
  const blocked = command.isPending || !active || !!failure?.stale;
  return (
    <section aria-label="Ustawienia reguł" className="card space-y-4">
      <h2 className="text-lg font-semibold">Co oznacza „bez kategorii”?</h2>
      <p className="text-sm text-gray-400">
        Wskaż istniejącą kategorię techniczną. Tylko nowe wydatki zapisane z tą
        kategorią mogą otrzymać kategorię z wcześniej zatwierdzonej reguły. Nie
        przeglądamy historii.
      </p>
      {!active ? (
        <p role="alert">Sesja zmieniła się. Wczytaj aktualne dane.</p>
      ) : null}
      <fieldset disabled={blocked || uncertain} className="space-y-3">
        <CategoryPicker
          id="rule-marker"
          label="Kategoria techniczna"
          categories={categories.data ?? []}
          value={marker}
          type="expense"
          onChange={(v) => {
            change();
            setMarker(v);
          }}
        />
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => {
              change();
              setEnabled(e.target.checked);
            }}
          />
          Włącz zatwierdzone reguły
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          Potwierdzam zakres przyszłych wydatków; stare wpisy i ręczne decyzje
          pozostają bez zmian
        </label>
      </fieldset>
      {failure ? (
        <p role="alert" className="text-sm text-red-400">
          {failure.message}
        </p>
      ) : null}
      {saved && active ? <p role="status">Ustawienia zapisane.</p> : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-primary"
          disabled={
            blocked ||
            !confirmed ||
            (enabled && !marker) ||
            categories.isError ||
            categories.isLoading
          }
          onClick={() => void save()}
        >
          Zapisz ustawienia
        </button>
        {failure?.stale ? (
          <button
            type="button"
            className="btn-secondary"
            disabled={command.isPending || !active}
            onClick={() => void refresh()}
          >
            Wczytaj aktualną wersję
          </button>
        ) : null}
      </div>
    </section>
  );
}

export function FinanceCategorizationSettings() {
  const session = useAuthStore((s) => s.sessionVersion);
  const settings = useCategorizationSettings();
  const rules = useCategorizationRules();
  const categories = useCategories();
  const command = useRuleCommand();
  const [editor, setEditor] = useState<{
    session: number;
    rule?: CategorizationRule;
  } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState<{
    id: string;
    version: number;
    action: "pause" | "retire";
    key: string;
  } | null>(null);
  async function changeRule(
    rule: CategorizationRule,
    action: "pause" | "retire",
  ) {
    const input =
      pending?.id === rule.id && pending.action === action
        ? pending
        : {
            id: rule.id,
            version: rule.version,
            action,
            key: crypto.randomUUID(),
          };
    setPending(input);
    try {
      await command.mutateAsync({
        session,
        method: "post",
        path: `/rules/${input.id}/${input.action}`,
        body: { expected_version: input.version },
        key: input.key,
      });
      if (useAuthStore.getState().sessionVersion === session) {
        setFailure(null);
        setPending(null);
      }
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session)
        setFailure(ruleError(error).message);
    }
  }
  const names = {
    draft: "Szkic",
    active: "Aktywna",
    paused: "Wstrzymana",
    retired: "Wycofana",
  };
  return (
    <div className="max-w-3xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Kategoryzacja</h1>
        <p className="mt-2 text-sm text-gray-400">
          Zatwierdzone reguły dla przyszłych ręcznych wydatków PLN. Importy
          Actual, dokumenty i historia nie są automatycznie zmieniane. Reguły
          nie wywołują AI; propozycje mają osobną zgodę i wymagają Twojego
          przeglądu.
        </p>
      </header>
      <QueryFeedback
        loading={settings.isLoading || categories.isLoading}
        error={settings.isError || categories.isError}
        errorMessage="Nie udało się pobrać ustawień lub kategorii."
        onRetry={() => {
          void settings.refetch();
          void categories.refetch();
        }}
      >
        {settings.data ? (
          <MarkerSettings key={session} snapshot={settings.data} />
        ) : null}
      </QueryFeedback>
      <SuggestionSettings />
      <section className="card space-y-4" aria-label="Reguły kategoryzacji">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Reguły</h2>
          <button
            className="btn-primary"
            type="button"
            disabled={
              !settings.data?.uncategorized_category_id || categories.isError
            }
            onClick={() => setEditor({ session })}
          >
            Nowa reguła
          </button>
        </div>
        {failure ? (
          <p role="alert" className="text-red-400">
            {failure}
          </p>
        ) : null}
        <QueryFeedback
          loading={rules.isLoading}
          error={rules.isError}
          errorMessage="Nie udało się pobrać reguł."
          onRetry={rules.refetch}
        >
          {!rules.data?.length ? (
            <p className="text-sm text-gray-400">
              Nie ma jeszcze reguł. Dodaj dokładny opis i sprawdź kategorię
              przed zatwierdzeniem.
            </p>
          ) : (
            <ul className="divide-y divide-gray-800">
              {rules.data.map((rule) => (
                <li key={rule.id} className="py-4 space-y-2">
                  <p className="font-mono text-sm [overflow-wrap:anywhere]">
                    {rule.display_description}
                  </p>
                  <p className="text-sm text-gray-400">
                    {categoryPath(
                      rule.target_category_id,
                      categories.data ?? [],
                    )}{" "}
                    · {names[rule.state]} · wersja {rule.version}
                  </p>
                  {rule.state !== "retired" ? (
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => setEditor({ session, rule })}
                      >
                        Edytuj / sprawdź
                      </button>
                      {rule.state === "active" ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={command.isPending}
                          onClick={() => void changeRule(rule, "pause")}
                        >
                          Wstrzymaj
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={command.isPending}
                        onClick={() => void changeRule(rule, "retire")}
                      >
                        Wycofaj
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </QueryFeedback>
      </section>
      {editor && editor.session === session && settings.data ? (
        <RuleEditor
          key={editor.rule?.id ?? "new"}
          rule={editor.rule}
          categories={categories.data ?? []}
          marker={settings.data.uncategorized_category_id}
          maxChars={settings.data.max_description_chars}
          onClose={() => setEditor(null)}
        />
      ) : null}
    </div>
  );
}
