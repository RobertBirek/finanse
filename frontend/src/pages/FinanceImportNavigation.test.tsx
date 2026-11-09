import { render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { FinanceTabs } from "../components/finance/FinanceTabs";
import { DocumentList } from "../components/DocumentList";
import {
  importTestWrapper,
  installImportServer,
} from "../test/bankImportFixtures";
import { processingDocument } from "../test/documentFixtures";

let server: ReturnType<typeof installImportServer>;
afterEach(() => server?.restore());

it("offers the existing-style Import tab", () => {
  server = installImportServer();
  render(importTestWrapper(<FinanceTabs />).node);
  expect(
    screen.getByRole("link", { name: "Import" }).getAttribute("href"),
  ).toMatch(/^\/finances\/imports/);
});

it("uses an existing PDF for import without invoice approval or a financial mutation", async () => {
  const document = processingDocument({
    id: "document-a",
    original_name: "bank.pdf",
    mime_type: "application/pdf",
    status: "done",
    processing_method: "bank_import",
    review: null,
  });
  server = installImportServer({
    onRequest: (request) =>
      request.url === "/documents" ? [document] : undefined,
  });
  render(importTestWrapper(<DocumentList />, "/documents").node);
  expect(
    await screen.findByRole("link", { name: "Użyj do importu" }),
  ).toHaveAttribute("href", "/finances/imports?document=document-a");
  expect(
    server.requests.filter((request) => request.method !== "get"),
  ).toHaveLength(0);
});
