import { useState } from "react";
import { ruleError } from "../../api/ruleErrors";
import type { Category } from "../../api/finance";
import {
  type CategorizationRule,
  type RulePreview,
  useRuleCommand,
  useRulePreview,
} from "../../api/categorizationRules";
import { useAuthStore } from "../../stores/authStore";
import { CategoryPicker } from "./CategoryPicker";
import { Dialog } from "../Dialog";
import api from "../../lib/api";

export function RuleEditor({
  rule,
  categories,
  marker,
  maxChars,
  onClose,
}: {
  rule?: CategorizationRule;
  categories: Category[];
  marker: string | null;
  maxChars: number;
  onClose: () => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const [saved, setSaved] = useState(rule);
  const [description, setDescription] = useState(
    rule?.display_description ?? "",
  );
  const [category, setCategory] = useState(rule?.target_category_id ?? "");
  const [preview, setPreview] = useState<RulePreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [failure, setFailure] = useState<ReturnType<typeof ruleError> | null>(
    null,
  );
  const [uncertain, setUncertain] = useState(false);
  const [pendingAction, setPendingAction] = useState<"save" | "approve" | null>(
    null,
  );
  const command = useRuleCommand();
  const check = useRulePreview();
  const busy = command.isPending || check.isPending;
  const dirty =
    !saved ||
    description !== saved.display_description ||
    category !== saved.target_category_id;
  function change() {
    setPreview(null);
    setConfirmed(false);
    setKey(crypto.randomUUID());
    setFailure(null);
  }
  async function save() {
    try {
      const value = (await command.mutateAsync({
        session,
        method: saved ? "patch" : "post",
        path: saved ? `/rules/${saved.id}` : "/rules",
        key,
        body: {
          display_description: description,
          target_category_id: category,
          ...(saved ? { expected_version: saved.version } : {}),
        },
      })) as CategorizationRule;
      if (useAuthStore.getState().sessionVersion !== session) return;
      setSaved(value);
      setPreview(null);
      setKey(crypto.randomUUID());
      setFailure(null);
      setUncertain(false);
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session) {
        const f = ruleError(error);
        setFailure(f);
        setUncertain(f.uncertain);
        setPendingAction("save");
      }
    }
  }
  async function review() {
    if (!saved) return;
    try {
      const value = await check.mutateAsync({
        session,
        id: saved.id,
        version: saved.version,
      });
      if (useAuthStore.getState().sessionVersion === session) {
        setPreview(value);
        setConfirmed(false);
        setKey(crypto.randomUUID());
        setFailure(null);
      }
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session)
        setFailure(ruleError(error));
    }
  }
  async function approve() {
    if (!saved || !preview || !confirmed) return;
    try {
      await command.mutateAsync({
        session,
        method: "post",
        path: `/rules/${saved.id}/approve`,
        key,
        body: {
          expected_version: saved.version,
          preview_snapshot: preview.preview_snapshot,
          confirm_future_only: true,
        },
      });
      if (useAuthStore.getState().sessionVersion === session) onClose();
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session) {
        const f = ruleError(error);
        setFailure(f);
        setUncertain(f.uncertain);
        setPendingAction("approve");
      }
    }
  }
  async function refresh() {
    try {
      const { data } = await api.get<CategorizationRule[]>(
        "/finance/categorization/rules",
      );
      if (useAuthStore.getState().sessionVersion !== session) return;
      const current = data.find((r) => r.id === saved?.id);
      setSaved(current);
      setPreview(null);
      setConfirmed(false);
      setFailure(null);
      setUncertain(false);
      setKey(crypto.randomUUID());
    } catch (error) {
      if (useAuthStore.getState().sessionVersion === session)
        setFailure(ruleError(error));
    }
  }
  const blocked = busy || !active || !!failure?.stale;
  return (
    <Dialog
      label="Reguła kategoryzacji"
      busy={busy}
      onClose={onClose}
      panelClassName="card w-full max-w-xl"
    >
      <h2 className="text-lg font-semibold">Reguła kategoryzacji</h2>
      <p className="my-3 text-sm text-gray-400">
        Dokładny opis, nie fragment ani wzorzec. Tylko nowe ręczne wydatki PLN z
        kategorią techniczną. Historia, importy Actual i ręczne przypisania są
        chronione.
      </p>
      {!active ? (
        <p role="alert">
          Sesja zmieniła się. Zamknij okno i wczytaj aktualne dane.
        </p>
      ) : null}
      <fieldset disabled={blocked || uncertain} className="space-y-3">
        <label className="block text-sm">
          Dokładny opis transakcji
          <input
            className="input mt-1"
            value={description}
            maxLength={maxChars}
            onChange={(e) => {
              change();
              setDescription(e.target.value);
            }}
          />
        </label>
        <CategoryPicker
          id="rule-target"
          label="Kategoria docelowa"
          categories={categories}
          type="expense"
          value={category}
          excludedIds={new Set(marker ? [marker] : [])}
          onChange={(value) => {
            change();
            setCategory(value);
          }}
        />
      </fieldset>
      {failure ? (
        <p role="alert" className="my-3 text-sm text-red-400">
          {failure.message}
        </p>
      ) : null}
      {failure?.stale ? (
        <button
          type="button"
          className="btn-secondary my-3"
          onClick={() => void refresh()}
          disabled={busy || !active}
        >
          Wczytaj aktualną wersję
        </button>
      ) : null}
      {preview ? (
        <section
          aria-label="Podgląd reguły"
          className="my-4 space-y-2 rounded-lg border border-advisor-500/40 p-3 [overflow-wrap:anywhere]"
        >
          <h3 className="font-semibold">
            Dokładne dopasowanie po normalizacji
          </h3>
          <p className="font-mono text-sm">
            {preview.grant.normalized_description_exact}
          </p>
          <p>Kategoria: {preview.grant.target_path}</p>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={blocked || uncertain}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Zatwierdzam dokładne dopasowanie dla przyszłych wydatków
          </label>
        </section>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary"
          disabled={
            blocked ||
            (uncertain && pendingAction === "approve") ||
            (!dirty && !uncertain) ||
            !description.trim() ||
            !category ||
            saved?.state === "retired"
          }
          onClick={() => void save()}
        >
          Zapisz szkic
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={
            blocked ||
            uncertain ||
            dirty ||
            !marker ||
            saved?.state === "active" ||
            saved?.state === "retired"
          }
          onClick={() => void review()}
        >
          Podgląd reguły
        </button>
        {preview ? (
          <button
            type="button"
            className="btn-primary"
            disabled={
              blocked || !confirmed || (uncertain && pendingAction === "save")
            }
            onClick={() => void approve()}
          >
            Zatwierdź dla przyszłych wydatków
          </button>
        ) : null}
        <button
          type="button"
          className="btn-secondary"
          onClick={onClose}
          disabled={busy}
        >
          Zamknij
        </button>
      </div>
    </Dialog>
  );
}
