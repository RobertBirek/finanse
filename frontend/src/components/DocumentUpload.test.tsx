import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { DocumentUpload } from "./DocumentUpload";

afterEach(() => vi.restoreAllMocks());

describe("DocumentUpload", () => {
  it("shows the required provider notice before file and camera controls", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: {
        max_file_bytes: 100,
        accepted_mime_types: ["image/jpeg"],
        automatic_image_vision: true,
        vision_provider_label: "Configured provider",
        vision_notice: null,
      },
    });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <DocumentUpload />
      </QueryClientProvider>,
    );

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent(
      "Zdjęcia są automatycznie wysyłane do Configured provider do odczytu AI. Dane wymagają sprawdzenia. Informacje widoczne na zdjęciu są przekazywane dostawcy.",
    );
    expect(
      notice.compareDocumentPosition(
        container.querySelector('input[capture="environment"]')!,
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("does not fabricate a provider brand when the backend label is absent", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: {
        max_file_bytes: 100,
        accepted_mime_types: ["image/jpeg"],
        automatic_image_vision: true,
        vision_provider_label: null,
        vision_notice: null,
      },
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <DocumentUpload />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Zdjęcia są automatycznie wysyłane do dostawcy do odczytu AI.",
    );
  });
});
