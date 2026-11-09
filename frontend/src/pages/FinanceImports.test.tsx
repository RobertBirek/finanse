import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { FinanceImports } from "./FinanceImports";
import { FinanceImportReview } from "./FinanceImportReview";
import {
  httpFailure,
  importTestWrapper,
  installImportServer,
  source,
} from "../test/bankImportFixtures";

let server: ReturnType<typeof installImportServer>;
afterEach(() => server?.restore());
function renderImportPage() {
  const value = importTestWrapper(
    <Routes>
      <Route path="/finances/imports" element={<FinanceImports />} />
      <Route
        path="/finances/imports/:batchId"
        element={<FinanceImportReview />}
      />
      <Route
        path="/other"
        element={<Link to="/finances/imports">Import</Link>}
      />
    </Routes>,
  );
  return render(value.node);
}
function userUpload(...files: File[]) {
  fireEvent.change(screen.getByLabelText("Pliki wyciągów"), {
    target: { files },
  });
  fireEvent.click(screen.getByRole("button", { name: "Dodaj pliki" }));
}

describe("bank statement upload", () => {
  it("keeps each file outcome and never commits on upload", async () => {
    server = installImportServer({
      onRequest: (request) => {
        if (
          request.url.endsWith("/sources") &&
          request.body instanceof FormData &&
          (request.body.get("file") as File).name === "bad.pdf"
        )
          throw httpFailure(422, {
            code: "pdf_encrypted",
            detail: "Zaszyfrowany PDF",
          });
      },
    });
    renderImportPage();
    await screen.findByRole("heading", { name: "Import wyciągów" });
    userUpload(
      new File(["synthetic"], "good.pdf", { type: "application/pdf" }),
      new File(["encrypted"], "bad.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByText(/bad.pdf.*Zaszyfrowany PDF/)).toBeVisible();
    expect(screen.getByText(/good.pdf.*Wymaga sprawdzenia/)).toBeVisible();
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(0);
  });
  it("opens the existing batch for a duplicate source instead of reparsing it", async () => {
    server = installImportServer({
      onRequest: (request) =>
        request.url.endsWith("/sources")
          ? { source, is_duplicate: true, existing_batch_id: "older-batch" }
          : undefined,
    });
    renderImportPage();
    await screen.findByRole("heading", { name: "Import wyciągów" });
    userUpload(new File(["same"], "same.pdf", { type: "application/pdf" }));
    expect(
      await screen.findByRole("link", { name: /Otwórz istniejący import/ }),
    ).toHaveAttribute("href", "/finances/imports/older-batch");
    expect(
      server.requests.filter((request) => request.url.endsWith("/prepare")),
    ).toHaveLength(0);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Dodaj pliki" })).toBeEnabled(),
    );
  });
});
