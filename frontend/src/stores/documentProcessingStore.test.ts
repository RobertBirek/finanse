import { beforeEach, describe, expect, it } from "vitest";
import { processingDocument } from "../test/documentFixtures";
import { useDocumentProcessingStore as store } from "./documentProcessingStore";

beforeEach(() => {
  store.getState().bindOwner(null);
  store.getState().bindOwner("owner");
});
const actor = () => ({
  ownerId: "owner",
  generation: store.getState().generation,
});
const ready = () => {
  const d = processingDocument();
  d.review!.status = "ready";
  d.review!.job_state = "succeeded";
  return d;
};
const observe = (d = processingDocument()) =>
  store.getState().observeDocument(actor(), d, store.getState().sequence);

describe("session document processing tracker", () => {
  it("observes an authoritative restore from another tab without accepting older replies", () => {
    observe();
    store.getState().clearDocumentFeedback(actor(), processingDocument().id);
    observe(processingDocument({ archived_at: null }));
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
  });
  it("accepts a fresh admitted operation after an external restore but fences pre-archive intents", () => {
    const old = { ...actor(), sequence: store.getState().sequence };
    store.getState().clearDocumentFeedback(actor(), processingDocument().id);
    const input = {
      key: "review:after-restore",
      operationId: "review:after-restore",
      documentId: processingDocument().id,
      source: "review" as const,
      kind: "ai" as const,
    };
    store.getState().register(old, input);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    store
      .getState()
      .register({ ...actor(), sequence: store.getState().sequence }, input);
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
  });
  it("clears only archived feedback and refuses a delayed active snapshot", () => {
    observe();
    const stale = store.getState().sequence;
    store.getState().clearDocumentFeedback(actor(), processingDocument().id);
    store.getState().observeDocument(actor(), processingDocument(), stale);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    expect(store.getState().toasts).toHaveLength(0);
  });
  it("allows newly requested work after restore, without accepting pre-archive replies", () => {
    observe();
    const stale = store.getState().sequence;
    store.getState().clearDocumentFeedback(actor(), processingDocument().id);
    store.getState().restoreDocumentFeedback(actor(), processingDocument().id);
    store.getState().observeDocument(actor(), processingDocument(), stale);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    observe();
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
  });
  it("does not let a previous session clear current document feedback", () => {
    const previous = actor();
    store.getState().bindOwner(null);
    store.getState().bindOwner("owner");
    observe();
    store.getState().clearDocumentFeedback(previous, processingDocument().id);
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
  });
  it("does not resurrect completed work from a delayed active-list response", () => {
    const pending = processingDocument();
    observe(pending);
    observe(ready());
    observe(pending);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    expect(store.getState().toasts).toHaveLength(1);
  });
  it("ignores stale legacy activity but discovers a genuinely later legacy run", () => {
    const pending = processingDocument({
      review: null,
      processing_method: "legacy_ocr",
      status: "pending",
      updated_at: "2026-11-03T00:00:00Z",
    });
    observe(pending);
    observe({ ...pending, status: "done", updated_at: "2026-11-03T00:00:02Z" });
    observe(pending);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
    observe({ ...pending, updated_at: "2026-11-03T00:00:03Z" });
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
  });
  it("does not toast already completed history on initial load", () => {
    observe(ready());
    expect(store.getState().toasts).toHaveLength(0);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
  it("observes active work, completes once and ignores StrictMode/refetch duplicates", () => {
    observe();
    expect(Object.keys(store.getState().watches)).toHaveLength(1);
    observe(ready());
    observe(ready());
    observe(ready());
    expect(store.getState().toasts).toHaveLength(1);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
  it("tracks an accepted fast completion even if the pending state was never polled", () => {
    store.getState().register(actor(), {
      key: "review:revision-1",
      operationId: "review:revision-1",
      documentId: ready().id,
      source: "review",
      kind: "ai",
    });
    observe(ready());
    expect(store.getState().toasts).toHaveLength(1);
  });
  it.each(["failed", "paused", "superseded", "unknown"])(
    "handles terminal/unknown state %s without false success",
    (state) => {
      observe();
      const d = processingDocument();
      d.review!.job_state = state;
      observe(d);
      expect(store.getState().toasts.some((t) => t.tone === "success")).toBe(
        false,
      );
      expect(store.getState().toasts).toHaveLength(
        state === "failed" || state === "paused" ? 1 : 0,
      );
      expect(Object.keys(store.getState().watches)).toHaveLength(
        state === "unknown" ? 1 : 0,
      );
    },
  );
  it("warns for incomplete results instead of announcing accurate extraction", () => {
    observe();
    const d = ready();
    d.review!.status = "incomplete";
    observe(d);
    expect(store.getState().toasts[0].tone).toBe("warning");
  });
  it("makes a new revision a new completion, without repeating an old revision", () => {
    observe();
    observe(ready());
    const next = processingDocument();
    next.review!.revision_id = "revision-2";
    next.review!.revision = 2;
    observe(next);
    next.review!.status = "ready";
    next.review!.job_state = "succeeded";
    observe(next);
    expect(store.getState().toasts).toHaveLength(2);
  });
  it("keeps OCR completion independent of an older AI review", () => {
    const d = ready();
    d.local_ocr_job_id = "ocr-1";
    d.local_ocr_state = "processing";
    observe(d);
    d.local_ocr_state = "succeeded";
    observe(d);
    expect(store.getState().toasts).toHaveLength(1);
    expect(store.getState().toasts[0].message).toContain("OCR");
  });
  it("fences old responses and mutation contexts across logout/relogin of the same user", () => {
    const old = actor();
    observe();
    store.getState().bindOwner(null);
    store.getState().bindOwner("owner");
    store.getState().observeDocument(old, ready(), 999);
    store.getState().register(old, {
      key: "old",
      documentId: ready().id,
      source: "review",
      kind: "ai",
    });
    expect(store.getState().toasts).toHaveLength(0);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
  it("does not expose another owner's document or keep toasts on user switch", () => {
    observe();
    observe(ready());
    store.getState().bindOwner("other");
    store
      .getState()
      .observeDocument(
        { ownerId: "other", generation: store.getState().generation },
        ready(),
        999,
      );
    expect(store.getState().toasts).toHaveLength(0);
    expect(Object.keys(store.getState().watches)).toHaveLength(0);
  });
  it("ignores an in-flight snapshot started before a new accepted run", () => {
    const earlier = store.getState().sequence;
    store.getState().register(actor(), {
      key: "fresh",
      documentId: ready().id,
      source: "review",
      kind: "ai",
    });
    store.getState().observeDocument(actor(), ready(), earlier);
    expect(store.getState().toasts).toHaveLength(0);
    observe(ready());
    expect(store.getState().toasts).toHaveLength(1);
  });
  it("permits explicit repeated legacy OCR runs with distinct accepted intent keys", () => {
    const d = processingDocument({
      review: null,
      processing_method: "legacy_ocr",
      status: "done",
    });
    for (const key of ["intent-1", "intent-2"]) {
      store.getState().register(actor(), {
        key,
        operationId: `legacy:${d.id}`,
        documentId: d.id,
        source: "legacy_ocr",
        kind: "ocr",
      });
      observe(d);
    }
    expect(store.getState().toasts).toHaveLength(2);
  });
  it("dismisses a toast without allowing completion refetch to recreate it", () => {
    observe();
    observe(ready());
    store.getState().dismiss(store.getState().toasts[0].id);
    observe(ready());
    expect(store.getState().toasts).toHaveLength(0);
  });
});
