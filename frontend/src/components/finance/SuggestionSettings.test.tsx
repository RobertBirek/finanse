import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, it, expect, vi } from "vitest";
import api from "../../lib/api";
import { SuggestionSettings } from "./SuggestionSettings";
import { useAuthStore } from "../../stores/authStore";

const scope = {
  version: 0,
  enabled: false,
  effective_enabled: false,
  available: true,
  blocked_reason: "consent_required",
  server_epoch: 1,
  configuration_fingerprint: "a".repeat(64),
  daily_call_limit: 5,
  max_description_chars: 500,
  max_categories: 200,
  review_page_size: 20,
  privacy_text: "Do AI wysyłamy opis i własny katalog kategorii.",
};
const usage = {
  usage_date: "2026-11-04",
  limit: 5,
  held: 0,
  dispatched: 2,
  known: 1,
  unknown: 1,
  released: 0,
  remaining_slots: 3,
  known_input_tokens: 100,
  known_output_tokens: 20,
  cost_status: "unpriced",
};
beforeEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ sessionVersion: 42 });
});
function mount(available = true) {
  vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/settings") ? { ...scope, available } : usage,
  }));
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <SuggestionSettings />
    </QueryClientProvider>,
  );
}
it("server-off blocks opt-in and does not claim unknown usage is free", async () => {
  mount(false);
  await screen.findByText(/Generowanie AI nie jest dostępne/);
  expect(
    screen.getByLabelText("Włącz propozycje AI dla nowych wydatków"),
  ).toBeDisabled();
  expect(screen.getByText(/Nieznane wywołania: 1/)).toBeInTheDocument();
  expect(screen.queryByText("0 zł")).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/model/i)).not.toBeInTheDocument();
});
it("enabling requires separate data-export and future-only consent", async () => {
  const saved = vi.spyOn(api, "patch").mockResolvedValue({
    data: { ...scope, version: 1, enabled: true, effective_enabled: true },
  });
  mount();
  await screen.findByLabelText("Włącz propozycje AI dla nowych wydatków");
  fireEvent.click(
    screen.getByLabelText("Włącz propozycje AI dla nowych wydatków"),
  );
  const save = screen.getByRole("button", { name: "Zapisz zgodę AI" });
  expect(save).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/Zgadzam się wysyłać opis/));
  expect(save).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/Tylko nowe wydatki/));
  fireEvent.click(save);
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(saved.mock.calls[0][1]).toEqual({
    expected_version: 0,
    enabled: true,
    expected_server_epoch: 1,
    expected_configuration_fingerprint: "a".repeat(64),
    confirm_future_only: true,
    confirm_data_export: true,
  });
  expect(saved.mock.calls[0][2]?.headers?.["Idempotency-Key"]).toBeTruthy();
});

it("an uncertain consent save keeps the same body/key and locks edits until resolved", async () => {
  const saved = vi
    .spyOn(api, "patch")
    .mockRejectedValueOnce(new Error("Disconnected"))
    .mockResolvedValue({
      data: { ...scope, version: 1, enabled: true, effective_enabled: true },
    });
  mount();
  await screen.findByLabelText("Włącz propozycje AI dla nowych wydatków");
  fireEvent.click(
    screen.getByLabelText("Włącz propozycje AI dla nowych wydatków"),
  );
  fireEvent.click(screen.getByLabelText(/Zgadzam się wysyłać opis/));
  fireEvent.click(screen.getByLabelText(/Tylko nowe wydatki/));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz zgodę AI" }));
  await screen.findByRole("button", { name: "Ponów zapis zgody AI" });
  expect(
    screen.getByLabelText("Włącz propozycje AI dla nowych wydatków"),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Ponów zapis zgody AI" }));
  await screen.findByText("Zgoda AI zapisana.");
  expect(saved.mock.calls[0]).toEqual(saved.mock.calls[1]);
});
