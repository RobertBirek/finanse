import { expect, it } from "vitest";
import { getFinanceDocumentStatus } from "./documentStatus";
import { isDocumentWorkActive } from "../../api/documents";
import { processingDocument } from "../../test/documentFixtures";

it("polls registration after recognition is finished and stops for review", () => {
  const document = processingDocument({
    review: null,
    status: "done",
    finance: { state: "pending", bill_id: null, review: null, lifecycle: null },
  });
  expect(isDocumentWorkActive(document)).toBe(true);
  expect(getFinanceDocumentStatus(document).label).toBe(
    "Szkic w kolejce",
  );
  document.finance!.state = "needs_review";
  expect(isDocumentWorkActive(document)).toBe(false);
  expect(getFinanceDocumentStatus(document).label).toBe("Do sprawdzenia");
});
