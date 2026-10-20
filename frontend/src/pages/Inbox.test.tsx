import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Inbox } from "./Inbox";

const state = vi.hoisted(() => ({ process: vi.fn(), failed: false }));

vi.mock("../api/inbox", () => ({
  useInboxItems: () => ({
    isLoading: false,
    data: [
      {
        id: "item-1",
        content: "Zaplanuj spotkanie",
        is_processed: false,
        created_at: "2026-10-20T10:00:00Z",
        agent_suggestion: null,
      },
    ],
  }),
  useCreateInboxItem: () => ({ mutate: vi.fn(), isPending: false }),
  useProcessInboxItem: () => ({
    mutate: state.process,
    isPending: false,
    isError: state.failed,
  }),
}));

beforeEach(() => {
  state.process.mockReset();
  state.failed = false;
});

describe("Inbox conversion safety", () => {
  it("disables unsupported project and transaction conversions", () => {
    render(<Inbox />);
    const project = screen.getByRole("button", { name: /Projekt.*wkrótce/ });
    const transaction = screen.getByRole("button", {
      name: /Transakcja.*wkrótce/,
    });
    expect(project).toBeDisabled();
    expect(transaction).toBeDisabled();
    fireEvent.click(project);
    fireEvent.click(transaction);
    expect(state.process).not.toHaveBeenCalled();
  });

  it("allows supported task conversion", () => {
    render(<Inbox />);
    fireEvent.click(screen.getByRole("button", { name: /Zadanie/ }));
    expect(state.process).toHaveBeenCalledWith({
      id: "item-1",
      target_type: "task",
    });
  });

  it("reports conversion failures instead of silently losing the action", () => {
    state.failed = true;
    render(<Inbox />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Nie udało się przetworzyć wpisu",
    );
    expect(screen.getByText("Zaplanuj spotkanie")).toBeInTheDocument();
  });
});
