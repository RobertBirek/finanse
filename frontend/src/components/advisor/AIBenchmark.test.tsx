import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import api from "../../lib/api";
import { AIBenchmark } from "./AIBenchmark";

it("runs only explicitly, keeps partial results and does not save either variant", async () => {
  const post = vi.spyOn(api, "post").mockResolvedValue({
    data: {
      suite_version: "advisor-v1",
      variants: [
        {
          model: "test-a",
          status: "partial",
          cases: [
            {
              case_id: "classify_task",
              status: "timeout",
              matches_expected: null,
              duration_ms: 15000,
              input_tokens: null,
              output_tokens: null,
            },
          ],
        },
        {
          model: "test-b",
          status: "ok",
          cases: [
            {
              case_id: "classify_task",
              status: "ok",
              matches_expected: true,
              duration_ms: 50,
              input_tokens: 12,
              output_tokens: 4,
            },
          ],
        },
      ],
    },
  });
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AIBenchmark />
      </QueryClientProvider>,
    );
    expect(post).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Model A"), {
      target: { value: "test-a" },
    });
    fireEvent.change(screen.getByLabelText("Model B"), {
      target: { value: "test-b" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Uruchom porównanie OpenAI" }),
    );
    expect(await screen.findByText(/Przekroczono czas/)).toBeVisible();
    expect(screen.getByText(/Zgodna z oczekiwaniem/)).toBeVisible();
    expect(screen.getByText(/Tokeny wejścia: —/)).toBeVisible();
    expect(post).toHaveBeenCalledExactlyOnceWith(
      "/advisor/settings/benchmark",
      {
        variants: [
          { model: "test-a", instructions: null },
          { model: "test-b", instructions: null },
        ],
      },
    );
  } finally {
    post.mockRestore();
  }
});
