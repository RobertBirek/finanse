import { describe, expect, it } from "vitest";
import { processingDocument } from "../../test/documentFixtures";
import {
  getDocumentOperations,
  getOperationNotice,
  isActiveOperation,
} from "./documentProcessing";

describe("document processing state", () => {
  it("uses revision identity and the real job state before stale review status", () => {
    const doc = processingDocument();
    doc.review!.status = "ready";
    const [operation] = getDocumentOperations(doc);
    expect(operation).toMatchObject({
      id: "review:revision-1",
      documentId: doc.id,
      kind: "ai",
      state: "processing",
    });
    expect(isActiveOperation(operation)).toBe(true);
    expect(getOperationNotice(operation)).toBeNull();
  });
  it("keeps local OCR separate from an older ready review", () => {
    const doc = processingDocument({
      local_ocr_job_id: "ocr-2",
      local_ocr_state: "pending",
    });
    doc.review!.status = "ready";
    doc.review!.job_state = "succeeded";
    const operations = getDocumentOperations(doc);
    expect(operations.find((x) => x.source === "local_ocr")).toMatchObject({
      id: "ocr:ocr-2",
      kind: "ocr",
      state: "pending",
    });
  });
  it.each(["paused", "superseded", "failed", "unknown"])(
    "never treats %s as active/success",
    (state) => {
      const doc = processingDocument();
      doc.review!.job_state = state;
      const [operation] = getDocumentOperations(doc);
      expect(isActiveOperation(operation)).toBe(false);
      expect(getOperationNotice(operation)?.tone).not.toBe("success");
    },
  );
  it("warns on incomplete output and says review, not correct, on ready output", () => {
    const doc = processingDocument();
    doc.review!.job_state = "succeeded";
    doc.review!.status = "incomplete";
    expect(getOperationNotice(getDocumentOperations(doc)[0])).toMatchObject({
      tone: "warning",
    });
    doc.review!.status = "ready";
    expect(getOperationNotice(getDocumentOperations(doc)[0])).toMatchObject({
      tone: "success",
      message: expect.stringContaining("sprawdź"),
    });
  });
  it("handles legacy OCR independently of AI review", () => {
    const doc = processingDocument({
      processing_method: "legacy_ocr",
      status: "pending",
      review: null,
    });
    expect(getDocumentOperations(doc)).toEqual([
      expect.objectContaining({
        id: `legacy:${doc.id}`,
        kind: "ocr",
        state: "pending",
        source: "legacy_ocr",
      }),
    ]);
    doc.status = "done";
    expect(getOperationNotice(getDocumentOperations(doc)[0])).toMatchObject({
      tone: "success",
      message: expect.stringContaining("OCR"),
    });
  });
});
