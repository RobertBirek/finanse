import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import api from "../lib/api";
import { AISettings } from "./AISettings";

it("does not display the saved key and clears the submitted key from the form", async () => {
  const get = vi.spyOn(api, "get").mockImplementation(async (path) => ({
    data:
      path === "/advisor/settings"
        ? {
            provider: "openai",
            model: null,
            server_model: "server-model",
            active_model: "server-model",
            credential_source: "custom",
            custom_key_available: true,
            server_models: ["server-model"],
            instructions: null,
          }
        : [],
  }));
  const put = vi.spyOn(api, "put").mockResolvedValue({ status: 200 });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  try {
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AISettings />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const key = await screen.findByLabelText("Nowy klucz API");
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("type", "password");
    fireEvent.change(key, { target: { value: "synthetic-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz klucz" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/advisor/settings/credential", {
        api_key: "synthetic-key",
      }),
    );
    expect(key).toHaveValue("");
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  } finally {
    put.mockRestore();
    get.mockRestore();
  }
});
