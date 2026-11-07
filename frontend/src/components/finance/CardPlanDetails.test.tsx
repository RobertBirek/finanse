import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CardPlanDetails } from "./CardPlanDetails";
import type { CardPlan } from "../../api/creditCards";
const mutateAsync = vi.hoisted(() => vi.fn());
vi.mock("../../api/creditCards", () => ({
  useCardMutation: () => ({ mutateAsync, isPending: false }),
}));
const plan: CardPlan = {
  id: "plan",
  name: "Komfort",
  principal_pln: 10000,
  remaining_principal_pln: 10000,
  source_transaction_id: "purchase",
  apr: "8.2500",
  fees_pln: 0,
  version: 1,
  status: "active",
  schedule_kind: "estimated",
  installments: [
    {
      number: 1,
      due_date: "2026-12-12",
      principal_pln: 10000,
      interest_pln: 69,
      fees_pln: 0,
    },
  ],
};
beforeEach(() => vi.clearAllMocks());
it("submits exact bank cents with an optimistic version, not another payment", async () => {
  mutateAsync.mockResolvedValue({});
  render(<CardPlanDetails accountId="card" plan={plan} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Uzgodnij harmonogram z bankiem" }),
  );
  fireEvent.change(screen.getByLabelText("interest_pln rata 1"), {
    target: { value: "0,67" },
  });
  fireEvent.submit(
    screen.getByRole("form", { name: "Harmonogram bankowy Komfort" }),
  );
  await vi.waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith({
      expected_version: 1,
      installments: [
        {
          number: 1,
          due_date: "2026-12-12",
          principal_pln: 10000,
          interest_pln: 67,
          fees_pln: 0,
        },
      ],
    }),
  );
});
it("retains bank inputs after a conflict and preserves paid history", async () => {
  mutateAsync.mockRejectedValue({
    response: { data: { detail: "Plan has payments" } },
  });
  render(<CardPlanDetails accountId="card" plan={plan} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Uzgodnij harmonogram z bankiem" }),
  );
  fireEvent.change(screen.getByLabelText("interest_pln rata 1"), {
    target: { value: "0,67" },
  });
  fireEvent.submit(
    screen.getByRole("form", { name: "Harmonogram bankowy Komfort" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Plan has payments",
  );
  expect(screen.getByLabelText("interest_pln rata 1")).toHaveValue("0,67");
});
it("keeps a closed plan visible without offering to overwrite its history", () => {
  render(
    <CardPlanDetails
      accountId="card"
      plan={{ ...plan, status: "closed", remaining_principal_pln: 0 }}
    />,
  );
  expect(screen.getByText("Zamknięty")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Uzgodnij/ }),
  ).not.toBeInTheDocument();
});
