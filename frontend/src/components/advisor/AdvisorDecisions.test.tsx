import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import api from "../../lib/api";
import { AdvisorDecisions } from "./AdvisorDecisions";

it("shows spending differences and leaves the provider idle until requested", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValue({
    data: {
      previous_start: "2026-10-23",
      current_start: "2026-11-06",
      end_exclusive: "2026-11-20",
      previous_total_pln: 10000,
      current_total_pln: 16000,
      delta_pln: 6000,
      categories: [{ category_id: "cat1", name: "Dom", delta_pln: 6000 }],
      transactions: [
        {
          transaction_id: "txn1",
          date: "2026-11-10",
          description: "Zakup",
          delta_pln: 16000,
        },
      ],
      truncated: true,
    },
  });
  const post = vi.spyOn(api, "post");
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AdvisorDecisions />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    screen
      .getByText("Co zmieniło moje wydatki?")
      .closest("details")
      ?.setAttribute("open", "");
    fireEvent.change(screen.getByLabelText("Długość porównania"), {
      target: { value: "14" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Porównaj wydatki" }));
    expect(await screen.findByText(/Różnica netto:.*60,00/)).toBeVisible();
    expect(screen.getByText(/Sumy obejmują wszystkie pozycje/)).toBeVisible();
    expect(get).toHaveBeenCalledExactlyOnceWith(
      "/advisor/decisions/spending-comparison",
      {
        params: { days: 14 },
      },
    );
    expect(post).not.toHaveBeenCalled();
  } finally {
    get.mockRestore();
    post.mockRestore();
  }
});

it("shows scenario assumptions and does not describe missing obligations as safe", async () => {
  const post = vi.spyOn(api, "post").mockResolvedValue({
    data: {
      baseline_minimum: { date: "2026-11-03", projected_balance_pln: 12000 },
      scenario_minimum: { date: "2026-11-03", projected_balance_pln: -3000 },
      first_negative_date: "2026-11-03",
      opening_balance_negative: false,
      next_payday: "2026-11-10",
      forecast_start: "2026-11-02",
      forecast_end: "2026-11-03",
      excluded_obligation_reasons: ["recurring_amount_unknown"],
      covers_day_before_payday: false,
    },
  });
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AdvisorDecisions />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const summary = screen.getByText("Symulator „co jeśli?”");
    summary.closest("details")?.setAttribute("open", "");
    fireEvent.change(screen.getByLabelText("Data wydatku"), {
      target: { value: "2026-11-02" },
    });
    fireEvent.change(screen.getByLabelText("Kwota wydatku (PLN)"), {
      target: { value: "150,00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Oblicz wariant" }));
    expect(
      await screen.findByText(/Prognoza pomija niektóre zobowiązania/),
    ).toBeVisible();
    expect(
      screen.getByText(/Prognoza nie obejmuje dnia przed wypłatą/),
    ).toBeVisible();
    expect(screen.queryByText(/wydatek bezpieczny/i)).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledExactlyOnceWith(
      "/advisor/decisions/cashflow-scenario",
      {
        expense_date: "2026-11-02",
        amount_pln_minor: 15000,
      },
    );
  } finally {
    post.mockRestore();
  }
});

it("loads source links only on demand and keeps facts after AI fails", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValue({
    data: {
      as_of: "2026-11-21",
      items: [
        {
          kind: "payment",
          source_id: "p1",
          title: "Czynsz",
          reason: "Termin płatności minął.",
          due_date: null,
          href: "/finances/cashflow",
        },
      ],
    },
  });
  const post = vi.spyOn(api, "post").mockRejectedValue(new Error("offline"));
  try {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AdvisorDecisions />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(get).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Co wymaga mojej uwagi?" }),
    );
    expect(await screen.findByText("Czynsz")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Otwórz prognozę płatności" }),
    ).toHaveAttribute("href", "/finances/cashflow");
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Objaśnij priorytety z OpenAI" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Objaśnienie jest niedostępne.",
    );
    expect(screen.getByText("Czynsz")).toBeVisible();
  } finally {
    get.mockRestore();
    post.mockRestore();
  }
});
