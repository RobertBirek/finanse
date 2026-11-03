import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import api from "../lib/api";
import { processingDocument } from "../test/documentFixtures";
import { DocumentViewer } from "./DocumentViewer";

afterEach(() => vi.restoreAllMocks());
it.each(["pending", "processing"] as const)(
  "shows actual %s AI work instead of unavailable OCR text",
  (state) => {
    const doc = processingDocument();
    doc.review = { ...doc.review!, status: state, job_state: state };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.spyOn(api, "get").mockResolvedValue({
      data: { extracted_text: "synthetic older OCR" },
    });
    render(
      <QueryClientProvider client={client}>
        <DocumentViewer document={doc} onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Dokument jest przetwarzany",
    );
    expect(
      screen.queryByText("Tekst OCR nie jest dostępny dla tego dokumentu."),
    ).not.toBeInTheDocument();
    client.clear();
  },
);
it.each(["pending", "processing"] as const)(
  "shows actual %s local OCR work ahead of old ready review/text",
  (state) => {
    const doc = processingDocument({
      has_extracted_text: true,
      local_ocr_job_id: "ocr-current",
      local_ocr_state: state,
    });
    doc.review = { ...doc.review!, status: "ready", job_state: "succeeded" };
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(["documents", doc.id, "text"], {
      extracted_text: "synthetic older OCR",
    });
    vi.spyOn(api, "get").mockResolvedValue({
      data: { extracted_text: "synthetic older OCR" },
    });
    render(
      <QueryClientProvider client={client}>
        <DocumentViewer document={doc} onClose={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Dokument jest przetwarzany",
    );
    expect(screen.queryByText("synthetic older OCR")).not.toBeInTheDocument();
    client.clear();
  },
);
