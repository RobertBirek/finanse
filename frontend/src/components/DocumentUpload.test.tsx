import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { DocumentUpload } from "./DocumentUpload";

afterEach(() => vi.restoreAllMocks());

describe("DocumentUpload", () => {
  const renderUpload = () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: {
        max_file_bytes: 100,
        accepted_mime_types: ["image/jpeg"],
        automatic_image_vision: false,
        vision_provider_label: null,
        vision_notice: null,
      },
    });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={client}>
        <DocumentUpload />
      </QueryClientProvider>,
    );
  };

  it.each([
    [
      "document_mime_unsupported",
      "Nieobsługiwany typ pliku. Wybierz PDF, JPG, PNG, HEIC lub HEIF.",
    ],
    ["document_empty", "Wybrany plik jest pusty. Wybierz go ponownie."],
    [
      "document_validation_failed",
      "Nie udało się odczytać pliku. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.",
    ],
    [
      "document_mime_mismatch",
      "Typ przesłanego pliku nie zgadza się z jego zawartością. Spróbuj wybrać oryginał przez Pliki zamiast biblioteki Zdjęć.",
    ],
  ])("shows the safe 400 diagnostic for %s", async (code, message) => {
    vi.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: { status: 400, data: { code, detail: "<untrusted>" } },
    });
    const { container } = renderUpload();

    fireEvent.change(
      container.querySelector<HTMLInputElement>(
        'input[type="file"]:not([capture])',
      )!,
      {
        target: {
          files: [
            new File(["safe"], "receipt.pdf", { type: "application/pdf" }),
          ],
        },
      },
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("does not render an unknown server detail", async () => {
    vi.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 400,
        data: { code: "unexpected", detail: "<b>private</b>" },
      },
    });
    const { container } = renderUpload();

    fireEvent.change(
      container.querySelector<HTMLInputElement>(
        'input[type="file"]:not([capture])',
      )!,
      {
        target: {
          files: [
            new File(["safe"], "receipt.pdf", { type: "application/pdf" }),
          ],
        },
      },
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nie udało się przesłać dokumentu.",
    );
    expect(screen.queryByText("<b>private</b>")).not.toBeInTheDocument();
  });

  it.each([
    [413, "Przekroczono limit pliku lub miejsca na dokumenty."],
    [503, "Przesyłanie jest chwilowo niedostępne. Spróbuj później."],
    [507, "Przesyłanie jest chwilowo niedostępne. Spróbuj później."],
  ])("keeps the existing %i upload message", async (status, message) => {
    vi.spyOn(api, "post").mockRejectedValue({
      isAxiosError: true,
      response: { status },
    });
    const { container } = renderUpload();

    fireEvent.change(
      container.querySelector<HTMLInputElement>(
        'input[type="file"]:not([capture])',
      )!,
      {
        target: {
          files: [
            new File(["safe"], "receipt.pdf", { type: "application/pdf" }),
          ],
        },
      },
    );

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(message),
    );
  });

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
