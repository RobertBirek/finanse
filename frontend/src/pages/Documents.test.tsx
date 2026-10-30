import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { Documents } from "./Documents";

afterEach(() => vi.restoreAllMocks());

function renderDocuments(
  status = "pending",
  next: string | null = "2026-10-22T12:00:00Z",
) {
  vi.spyOn(api, "get").mockResolvedValue({
    data: [
      {
        id: "one",
        original_name: "saved.pdf",
        status,
        size_bytes: 200,
        created_at: "2026-10-22T10:00:00Z",
        next_attempt_at: next,
        attempt_count: 1,
        last_error_code: "upstream_unavailable",
      },
    ],
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Documents />
    </QueryClientProvider>,
  );
}

describe("document retry and admission feedback", () => {
  it("camera_requests_environment_and_accepts_heic", () => {
    const view = renderDocuments("done", null);
    const camera = view.container.querySelector(
      'input[capture="environment"]',
    ) as HTMLInputElement;
    expect(camera).toBeTruthy();
    expect(camera.accept).toContain(".heic");
    expect(camera.accept).toContain(".heif");
  });
  it("multi_upload_shows_per_file_success_failure", async () => {
    vi.spyOn(api, "post")
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 503 } })
      .mockResolvedValueOnce({ data: { document: {}, is_duplicate: false } });
    const view = renderDocuments("done", null);
    const input = view.container.querySelector('input[type="file"]')!;
    fireEvent.change(input, {
      target: {
        files: [
          new File(["a"], "first.pdf", { type: "application/pdf" }),
          new File(["b"], "second.pdf", { type: "application/pdf" }),
        ],
      },
    });
    expect(await screen.findByText("Przesłano")).toBeInTheDocument();
    expect(
      screen.getAllByRole("status").some((node) => node.textContent === "Błąd"),
    ).toBe(true);
    expect(api.post).toHaveBeenCalledTimes(2);
  });
  it("shows scheduled retry without promising success", async () => {
    renderDocuments();
    expect(await screen.findByText(/Ponowna próba/)).toBeInTheDocument();
  });
  it("does not promise another retry for terminal failures", async () => {
    renderDocuments("error", null);
    await screen.findByRole("button", { name: "Otwórz dokument: saved.pdf" });
    expect(screen.queryByText(/Ponowna próba/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Przetwarzanie zakończone błędem/),
    ).toBeInTheDocument();
  });
  it.each([413, 503, 507])(
    "announces upload rejection %s without success",
    async (status) => {
      vi.spyOn(api, "post").mockRejectedValue({
        isAxiosError: true,
        response: { status },
      });
      const view = renderDocuments("done", null);
      fireEvent.change(view.container.querySelector("input[type=file]")!, {
        target: {
          files: [new File(["pdf"], "new.pdf", { type: "application/pdf" })],
        },
      });
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(
        status === 413 ? /limit/i : /Spróbuj później/,
      );
      expect(screen.queryByText(/Dokument przesłany/)).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Otwórz dokument: new.pdf" }),
      ).not.toBeInTheDocument();
    },
  );
});
