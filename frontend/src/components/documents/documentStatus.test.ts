import { describe, expect, it } from "vitest";
import { getDocumentStatus } from "./documentStatus";

describe("getDocumentStatus", () => {
  it("uses the review status instead of the technical document completion", () => {
    expect(
      getDocumentStatus({
        status: "done",
        review: {
          revision_id: "revision-1",
          revision: 1,
          input_method: "image",
          status: "incomplete",
          error_code: null,
          warnings: [],
          job_state: "succeeded",
        },
      }),
    ).toMatchObject({ label: "Uzupełnij ręcznie" });
  });

  it("labels failed AI reviews without claiming OCR completion", () => {
    expect(
      getDocumentStatus({
        status: "done",
        review: {
          revision_id: "revision-1",
          revision: 1,
          input_method: "image",
          status: "error",
          error_code: "daily_limit_reached",
          warnings: [],
          job_state: "failed",
        },
      }),
    ).toMatchObject({ label: "Limit odczytów AI" });
  });

  it("surfaces a terminal provider error from an incomplete vision review", () => {
    expect(
      getDocumentStatus({
        status: "done",
        review: {
          revision_id: "revision-1",
          revision: 1,
          input_method: "image",
          status: "incomplete",
          error_code: "configuration_missing",
          warnings: [],
          job_state: "failed",
        },
      }),
    ).toMatchObject({ label: "AI niedostępne", tone: "danger" });
  });
});
