import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CardEstimate } from "./CardEstimate";
const mutateAsync = vi.hoisted(() => vi.fn());
vi.mock("../../api/creditCards", () => ({
  useCardMutation: () => ({ mutateAsync, isPending: false }),
}));
it("does not show an old estimate after its principal changed while waiting", async () => {
  let resolve!: (value: unknown) => void;
  mutateAsync.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  render(<CardEstimate accountId="card" apr="14.50" />);
  fireEvent.change(screen.getByLabelText("Oprocentowany kapitał PLN"), {
    target: { value: "1000" },
  });
  fireEvent.change(screen.getByLabelText("Liczba dni"), {
    target: { value: "30" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "Szacunek odsetek" }));
  fireEvent.change(screen.getByLabelText("Oprocentowany kapitał PLN"), {
    target: { value: "2000" },
  });
  await act(async () => resolve({ estimated_interest_pln: 1192 }));
  expect(screen.queryByText(/11,92 PLN/)).not.toBeInTheDocument();
});
