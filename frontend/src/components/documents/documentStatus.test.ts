import { describe, expect, it } from "vitest";
import { getDocumentStatus } from "./documentStatus";

describe("getDocumentStatus", () => {
  it.each(["incomplete", "error"] as const)(
    "labels a recovered exhausted job as interrupted (%s)",
    (status) => {
      expect(
        getDocumentStatus({
          status: "done",
          review: {
            revision_id: "legacy-failed",
            revision: 1,
            input_method: "image",
            status,
            error_code: "attempts_exhausted",
            warnings: [],
            job_state: "failed",
          },
        }),
      ).toMatchObject({ label: "Odczyt AI przerwany", tone: "warning" });
    },
  );
  it.each(["incomplete", "error"] as const)(
    "distinguishes invalid AI data from provider outage for %s",
    (status) => {
      expect(
        getDocumentStatus({
          status: "done",
          review: {
            revision_id: "synthetic",
            revision: 1,
            input_method: "image",
            status,
            error_code: "invalid_model_output",
            warnings: [],
            job_state: "failed",
          },
        }),
      ).toMatchObject({ label: "Nieprawidłowy wynik AI", tone: "warning" });
    },
  );
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

  it.each([
    "provider_unavailable",
    "provider_auth_failed",
    "provider_timeout",
    "provider_response_too_large",
  ])("labels terminal %s provider errors as unavailable", (error_code) => {
    expect(
      getDocumentStatus({
        status: "done",
        review: {
          revision_id: "revision-1",
          revision: 1,
          input_method: "image",
          status: "incomplete",
          error_code,
          warnings: [],
          job_state: "failed",
        },
      }),
    ).toMatchObject({ label: "AI niedostępne", tone: "danger" });
  });
});
