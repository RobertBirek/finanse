import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useDocumentProcessingStore as store } from "../../stores/documentProcessingStore";
import { processingDocument } from "../../test/documentFixtures";
import { ProcessingFeedback } from "./ProcessingFeedback";

beforeEach(() => {
  store.getState().bindOwner(null);
  store.getState().bindOwner("owner");
});
afterEach(() => {
  document.querySelectorAll("dialog").forEach((d) => d.remove());
  store.getState().bindOwner(null);
});
function mountToast() {
  const actor = { ownerId: "owner", generation: store.getState().generation };
  const doc = processingDocument();
  store.getState().observeDocument(actor, doc, store.getState().sequence);
  doc.review!.status = "ready";
  doc.review!.job_state = "succeeded";
  store.getState().observeDocument(actor, doc, store.getState().sequence);
  return render(
    <MemoryRouter>
      <ProcessingFeedback actor={actor} watches={[]} hasError={false} />
    </MemoryRouter>,
  );
}
describe("accessible processing toasts", () => {
  it("places notifications in the native modal top layer when a document dialog is open", async () => {
    const dialog = document.createElement("dialog");
    document.body.append(dialog);
    dialog.showModal();
    mountToast();
    const region = screen.getByRole("region", {
      name: "Powiadomienia o odczycie",
    });
    expect(region.closest("dialog")).toBe(dialog);
    act(() => dialog.close());
    await waitFor(() =>
      expect(
        screen
          .getByRole("region", { name: "Powiadomienia o odczycie" })
          .closest("dialog"),
      ).toBeNull(),
    );
    expect(
      screen.getByRole("link", { name: "Otwórz dokument" }),
    ).toHaveAttribute("href", expect.stringContaining("/documents?review="));
  });
});
