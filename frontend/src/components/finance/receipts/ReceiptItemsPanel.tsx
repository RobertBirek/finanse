import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { AxiosError } from "axios";
import {
  useReceiptItems,
  useReceiptPaymentContext,
  useSaveReceiptDraft,
  useDiscardReceiptDraft,
  useApproveReceiptItems,
  usePreviewReceiptPayment,
  useApplyReceiptPayment,
} from "../../../api/receiptItems";
import type {
  ReceiptItemsContext,
  ReceiptPaymentPreview,
  ReceiptCommandInput,
} from "../../../api/receiptItems";
import { useCategories } from "../../../api/finance";
import { useAuthStore } from "../../../stores/authStore";
import { Dialog } from "../../Dialog";
import { ReceiptStorePicker } from "./ReceiptStorePicker";
import { ReceiptLineEditor } from "./ReceiptLineEditor";
import { ReceiptDiscountEditor } from "./ReceiptDiscountEditor";
import { ReceiptPaymentReview } from "./ReceiptPaymentReview";
import { ReceiptReadPanel } from "./ReceiptReadPanel";
import { ReceiptReadEvidence } from "./ReceiptReadEvidence";
import { fromReceiptBody, toReceiptBody } from "./receiptDraft";
import type { ReceiptDraft } from "./receiptDraft";
import { formatPLN } from "../../../lib/format";

type Action = "save" | "discard" | "approve" | "apply";
export function ReceiptItemsPanel({
  billId,
  onClose,
}: {
  billId: string;
  onClose: () => void;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const query = useReceiptItems(billId);
  return query.data ? (
    <Editor
      key={`${session}:${billId}`}
      initial={query.data}
      onClose={onClose}
      refresh={async () => {
        const r = await query.refetch();
        if (r.isError) throw new Error("receipt_reload_failed");
        return r.data;
      }}
    />
  ) : (
    <Dialog label="Produkty i kategorie" onClose={onClose}>
      {query.isError ? (
        <p role="alert">
          Nie udało się pobrać pozycji.{" "}
          <button type="button" onClick={() => void query.refetch()}>
            Spróbuj ponownie
          </button>
        </p>
      ) : (
        <p>Wczytywanie pozycji…</p>
      )}
    </Dialog>
  );
}
function Editor({
  initial,
  onClose,
  refresh,
}: {
  initial: ReceiptItemsContext;
  onClose: () => void;
  refresh: () => Promise<ReceiptItemsContext | undefined>;
}) {
  const [session] = useState(() => useAuthStore.getState().sessionVersion);
  const active = useAuthStore((s) => s.sessionVersion) === session;
  const [snapshot, setSnapshot] = useState(initial);
  const [draft, setDraft] = useState<ReceiptDraft>(() =>
    fromReceiptBody(
      (initial.draft ?? initial.approved)?.body ?? {
        store_id: null,
        store_version: null,
        lines: [],
        discounts: [],
      },
    ),
  );
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [storeBusy, setStoreBusy] = useState(false),
    [unknown, setUnknown] = useState(false),
    [message, setMessage] = useState<string | null>(null),
    [closing, setClosing] = useState(false);
  const [preview, setPreview] = useState<ReceiptPaymentPreview | null>(null);
  const [importLocked, setImportLocked] = useState(false);
  const importLockRef = useRef(false);
  const [reviewKeys, setReviewKeys] = useState<string[] | null>(null);
  const evidence = (snapshot.draft ?? snapshot.approved)?.evidence;
  const intent = useRef<{ action: Action; input: ReceiptCommandInput } | null>(
      null,
    ),
    busyRef = useRef(false);
  const save = useSaveReceiptDraft(),
    discard = useDiscardReceiptDraft(),
    approve = useApproveReceiptItems(),
    apply = useApplyReceiptPayment(),
    previewCommand = usePreviewReceiptPayment();
  const payment = useReceiptPaymentContext(snapshot.bill_id),
    categories = useCategories();
  const current = () => session === useAuthStore.getState().sessionVersion;
  const locked =
    !active ||
    busy ||
    unknown ||
    storeBusy ||
    importLocked ||
    !snapshot.editable;
  function edit(value: ReceiptDraft) {
    if (importLockRef.current) return;
    setDraft(value);
    setDirty(true);
    setPreview(null);
    setMessage(null);
    setReviewKeys([]);
  }
  function canonical(value: ReceiptItemsContext) {
    setReviewKeys(null);
    setSnapshot(value);
    setDraft(
      fromReceiptBody(
        (value.draft ?? value.approved)?.body ?? {
          store_id: null,
          store_version: null,
          lines: [],
          discounts: [],
        },
      ),
    );
    setDirty(false);
    setPreview(null);
  }
  async function run(action: Action) {
    if (busyRef.current || !current() || storeBusy || importLockRef.current)
      return;
    let captured = intent.current;
    if (!captured) {
      let body: Record<string, unknown>;
      try {
        if (action === "save")
          body = {
            expected_version: snapshot.state_version,
            expected_bill_version: snapshot.bill_version,
            body: toReceiptBody(draft),
            ...(evidence && reviewKeys !== null
              ? {
                  extraction_review: {
                    extraction_id: evidence.extraction_id,
                    expected_extraction_sha256: evidence.extraction_sha256,
                    acknowledged_problem_keys: reviewKeys,
                  },
                }
              : {}),
          };
        else if (action === "discard")
          body = { expected_version: snapshot.state_version };
        else if (action === "approve") {
          if (!snapshot.draft) return;
          body = {
            expected_version: snapshot.state_version,
            draft_revision_id: snapshot.draft.id,
            expected_body_sha256: snapshot.draft.body_sha256,
            confirmed: true,
          };
        } else {
          if (!preview) return;
          body = {
            expected_state_version: preview.expected_state_version,
            approved_revision_id: preview.approved_revision_id,
            expected_preview_snapshot: preview.preview_snapshot,
            confirmed: true,
          };
        }
      } catch (error) {
        setMessage((error as Error).message);
        return;
      }
      captured = {
        action,
        input: {
          session,
          billId: snapshot.bill_id,
          key: crypto.randomUUID(),
          body,
        },
      };
      intent.current = captured;
    }
    busyRef.current = true;
    setBusy(true);
    setMessage(null);
    try {
      if (captured.action === "apply") {
        await apply.mutateAsync(captured.input);
        if (!current()) return;
        const value = await refresh();
        if (!current()) return;
        if (value) canonical(value);
        setMessage("Podział zatwierdzony. Nie utworzono nowej płatności.");
      } else {
        const command =
          captured.action === "save"
            ? save
            : captured.action === "approve"
              ? approve
              : discard;
        await command.mutateAsync(captured.input);
        if (!current()) return;
        const value = await refresh();
        if (!current()) return;
        if (value) canonical(value);
        setMessage(
          captured.action === "approve"
            ? "Pozycje zatwierdzone. Podział płatności wymaga osobnego przeglądu."
            : captured.action === "save"
              ? "Szkic zapisany."
              : "Szkic odłożony; historia pozostała zachowana.",
        );
      }
      if (current()) {
        intent.current = null;
        setUnknown(false);
      }
    } catch (error) {
      if (current()) {
        const status = (error as AxiosError<{ detail?: string }>).response
          ?.status;
        const uncertain = !status || status >= 500;
        setUnknown(uncertain);
        if (!uncertain) {
          intent.current = null;
          setPreview(null);
        }
        setMessage(
          uncertain
            ? "Wynik operacji jest nieznany. Ponów tę samą operację z zachowanym kluczem."
            : status === 409
              ? "Dane zmieniły się. Twoje wpisy pozostały; wczytaj aktualne dane przed kolejną decyzją."
              : "Nie udało się zapisać. Sprawdź dane, uprawnienia i sumy.",
        );
      }
    } finally {
      busyRef.current = false;
      if (current()) setBusy(false);
    }
  }
  async function prepare() {
    if (
      locked ||
      dirty ||
      !snapshot.approved ||
      snapshot.draft ||
      busyRef.current
    )
      return;
    busyRef.current = true;
    setBusy(true);
    try {
      const p = await previewCommand.mutateAsync({
        session,
        billId: snapshot.bill_id,
        body: {
          expected_state_version: snapshot.state_version,
          approved_revision_id: snapshot.approved.id,
        },
      });
      if (current()) {
        setPreview(p);
        setMessage(null);
      }
    } catch {
      if (current()) {
        setPreview(null);
        setMessage(
          "Nie można przygotować podziału. Sprawdź aktualne pozycje i powiązanie całej płatności.",
        );
      }
    } finally {
      busyRef.current = false;
      if (current()) setBusy(false);
    }
  }
  async function reload() {
    if (busyRef.current || !current() || importLockRef.current) return;
    const value = await refresh();
    if (value && current()) {
      canonical(value);
      intent.current = null;
      setUnknown(false);
      setMessage(null);
    }
  }
  const excluded = new Set(
    (categories.data ?? [])
      .filter((c) => !snapshot.eligible_category_ids.includes(c.id))
      .map((c) => c.id),
  );
  const calculation = snapshot.calculation;
  function requestClose() {
    if (dirty || unknown || busy || storeBusy || importLocked) setClosing(true);
    else onClose();
  }
  return (
    <Dialog
      label="Produkty i kategorie"
      onClose={requestClose}
      panelClassName="card w-full max-w-3xl p-4 sm:p-6"
    >
      <div className="space-y-4 [overflow-wrap:anywhere]">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-xl font-semibold">Produkty i kategorie</h2>
          <button
            type="button"
            className="btn-secondary"
            onClick={requestClose}
          >
            Zamknij produkty
          </button>
        </div>
        <p className="text-sm text-gray-400">
          Wpisz produkty ręcznie lub świadomie przenieś propozycję ze zdjęcia.
          Zatwierdzenie pozycji nie zmienia płatności.
        </p>
        {!active ? (
          <p role="alert">Sesja zmieniła się. Wczytaj aktualne dane.</p>
        ) : null}
        {!snapshot.editable ? (
          <p role="alert">
            Edycja wymaga aktywnego zatwierdzonego paragonu PLN.
          </p>
        ) : null}
        {active ? (
          <ReceiptReadPanel
            billId={snapshot.bill_id}
            dirty={dirty}
            disabled={
              !active || busy || unknown || storeBusy || !snapshot.editable
            }
            onImportLockChange={(value) => {
              importLockRef.current = value;
              setImportLocked(value);
            }}
            onImported={async () => {
              const value = await refresh();
              if (!value || !current())
                throw new Error("receipt_reload_failed");
              canonical(value);
            }}
          />
        ) : null}
        {evidence ? (
          <ReceiptReadEvidence
            billId={snapshot.bill_id}
            evidence={evidence}
            selected={reviewKeys}
            disabled={locked}
            onChange={(keys) => {
              setReviewKeys(keys);
              setDirty(true);
              setPreview(null);
            }}
          />
        ) : null}
        <ReceiptStorePicker
          storeId={draft.store_id}
          disabled={
            !active || busy || unknown || importLocked || !snapshot.editable
          }
          maxName={snapshot.limits.store_name_max_chars}
          onBusyChange={setStoreBusy}
          onChange={(s) =>
            edit({
              ...draft,
              store_id: s.id,
              store_version: s.version,
              lines: draft.lines.map((l) => ({ ...l, hint: null })),
            })
          }
        />
        <fieldset disabled={locked} className="space-y-4">
          <legend className="text-lg font-semibold">Produkty</legend>
          {draft.lines.map((line, index) => (
            <ReceiptLineEditor
              key={line.line_key}
              line={line}
              index={index}
              billId={snapshot.bill_id}
              storeId={draft.store_id}
              categories={categories.data ?? []}
              excludedIds={excluded}
              disabled={locked}
              maxName={snapshot.limits.item_name_max_chars}
              onChange={(value) =>
                edit({
                  ...draft,
                  lines: draft.lines.map((l) =>
                    l.line_key === value.line_key ? value : l,
                  ),
                })
              }
              onDelete={() => {
                if (
                  draft.discounts.some((d) =>
                    (d.shares[line.line_key] ?? "").trim(),
                  )
                ) {
                  setMessage(
                    "Najpierw usuń lub przenieś udziały rabatu tego produktu.",
                  );
                  return;
                }
                edit({
                  ...draft,
                  lines: draft.lines.filter(
                    (l) => l.line_key !== line.line_key,
                  ),
                });
              }}
            />
          ))}
          <button
            type="button"
            className="btn-secondary"
            disabled={draft.lines.length >= snapshot.limits.max_lines}
            onClick={() =>
              edit({
                ...draft,
                lines: [
                  ...draft.lines,
                  {
                    line_key: crypto.randomUUID(),
                    name: "",
                    amount: "",
                    category_id: null,
                    hint: null,
                  },
                ],
              })
            }
          >
            Dodaj produkt
          </button>
          <h3 className="font-semibold">Rabaty wpisane osobno</h3>
          {draft.discounts.map((discount, index) => (
            <ReceiptDiscountEditor
              key={discount.discount_key}
              discount={discount}
              index={index}
              lines={draft.lines}
              disabled={locked}
              maxName={snapshot.limits.item_name_max_chars}
              onChange={(value) =>
                edit({
                  ...draft,
                  discounts: draft.discounts.map((d) =>
                    d.discount_key === value.discount_key ? value : d,
                  ),
                })
              }
              onDelete={() =>
                edit({
                  ...draft,
                  discounts: draft.discounts.filter(
                    (d) => d.discount_key !== discount.discount_key,
                  ),
                })
              }
            />
          ))}
          <button
            type="button"
            className="btn-secondary"
            disabled={draft.discounts.length >= snapshot.limits.max_discounts}
            onClick={() =>
              edit({
                ...draft,
                discounts: [
                  ...draft.discounts,
                  {
                    discount_key: crypto.randomUUID(),
                    name: "",
                    amount: "",
                    shares: {},
                  },
                ],
              })
            }
          >
            Dodaj rabat
          </button>
        </fieldset>
        {categories.isError ? (
          <p role="alert">
            Nie udało się pobrać kategorii.{" "}
            <button type="button" onClick={() => void categories.refetch()}>
              Ponów listę kategorii
            </button>
          </p>
        ) : null}
        <Link
          className="block text-sm underline"
          to="/settings/finances/categories"
        >
          Utwórz kategorię osobno
        </Link>
        {calculation ? (
          <section
            className="rounded bg-gray-800 p-3 text-sm"
            aria-label="Kontrola sum zapisanych pozycji"
          >
            <p>
              Suma zapisanych pozycji po rabatach:{" "}
              {calculation.net_total_minor === null
                ? "niepełna"
                : `${formatPLN(calculation.net_total_minor)} zł`}
            </p>
            <p>
              Różnica do paragonu:{" "}
              {calculation.difference_minor === null
                ? "nieznana"
                : `${formatPLN(calculation.difference_minor)} zł`}
            </p>
            {dirty ? (
              <p>
                Masz niezapisane zmiany. Powyższe sumy dotyczą zapisanej wersji.
              </p>
            ) : null}
            <ul>
              {[
                ...calculation.problems,
                ...(snapshot.draft?.problems ??
                  snapshot.approved?.problems ??
                  []),
              ]
                .filter(
                  (p, i, a) =>
                    a.findIndex((other) => other.message === p.message) === i,
                )
                .map((p, i) => (
                  <li key={i}>{p.message}</li>
                ))}
            </ul>
          </section>
        ) : null}
        {message ? (
          <p role="status" className="text-sm">
            {message}
          </p>
        ) : null}
        {(initial.state_version !== snapshot.state_version ||
          initial.bill_version !== snapshot.bill_version ||
          message?.startsWith("Dane zmieniły się")) &&
        !unknown ? (
          <div className="text-sm">
            <p>Zapisana wersja może być inna. Wpisy nie zostały zastąpione.</p>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy || storeBusy || importLocked || !active}
              onClick={() => setClosing(true)}
            >
              Wczytaj aktualne dane
            </button>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {unknown ? (
            <>
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !active}
                onClick={() => void run(intent.current?.action ?? "save")}
              >
                Ponów tę samą operację
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={busy || !active}
                onClick={() => setClosing(true)}
              >
                Porzuć próbę i sprawdź zapis
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn-primary"
                disabled={locked}
                onClick={() => void run("save")}
              >
                Zapisz robocze
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={locked || dirty || !snapshot.draft?.current}
                onClick={() => void run("approve")}
              >
                Zatwierdź pozycje
              </button>
              {snapshot.draft ? (
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={locked}
                  onClick={() => void run("discard")}
                >
                  Odrzuć szkic
                </button>
              ) : null}
            </>
          )}
        </div>
        {payment.isError ? (
          <p role="alert">Nie udało się sprawdzić powiązania płatności.</p>
        ) : !payment.data?.allowed ? (
          <p className="text-sm">
            {payment.data?.blocked_reason ?? "Sprawdzanie płatności…"}{" "}
            <Link
              className="underline"
              to={`/finances/documents?bill=${snapshot.bill_id}`}
            >
              Wróć do rozliczenia dokumentu
            </Link>
          </p>
        ) : null}
        {payment.data?.last_application ? (
          <p className="text-sm">
            {payment.data.last_application.items_changed ||
            payment.data.last_application.ledger_changed
              ? "Pozycje lub księga zmieniły się od ostatniego podziału."
              : "Ostatni podział odpowiada zapisanej wersji."}
          </p>
        ) : null}
        {!preview ? (
          <button
            type="button"
            className="btn-primary"
            disabled={
              locked ||
              dirty ||
              !!snapshot.draft ||
              !snapshot.approved?.current ||
              !payment.data?.allowed
            }
            onClick={() => void prepare()}
          >
            Sprawdź podział płatności
          </button>
        ) : (
          <ReceiptPaymentReview
            preview={preview}
            categories={categories.data ?? []}
            disabled={locked || dirty}
            onConfirm={() => void run("apply")}
            onCancel={() => setPreview(null)}
          />
        )}
        {closing ? (
          <section
            className="space-y-2 rounded border border-amber-500 p-3"
            aria-label="Potwierdź porzucenie"
          >
            <p>
              Niezapisane zmiany przepadną. Nieznana operacja mogła już zostać
              zapisana; nie wysyłamy jej ponownie bez Twojej decyzji.
            </p>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy || storeBusy}
              onClick={() => setClosing(false)}
            >
              Zostań przy edycji
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy || storeBusy}
              onClick={onClose}
            >
              Zamknij mimo to
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy || storeBusy || !active}
              onClick={() => {
                setClosing(false);
                void reload();
              }}
            >
              Porzuć wpisy i wczytaj aktualne
            </button>
          </section>
        ) : null}
      </div>
    </Dialog>
  );
}
