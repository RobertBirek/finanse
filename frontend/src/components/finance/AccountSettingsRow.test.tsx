import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountRow } from "./AccountSettingsRow";

const account = {
  id: "checking",
  name: "Rachunek główny",
  type: "checking",
  currency: "PLN",
  is_active: true,
  is_budget_account: true,
  balance_pln: 100000,
  opened_at: "2026-01-01",
  closed_at: null,
  iban: "PL61109010140000071219812874",
};

function props(
  overrides: Partial<ComponentProps<typeof AccountRow>> = {},
): ComponentProps<typeof AccountRow> {
  return {
    account,
    updateMutation: {
      mutate: vi.fn(),
      isPending: false,
      variables: undefined,
      error: null,
    } as never,
    deleteMutation: {
      mutate: vi.fn(),
      isPending: false,
      variables: undefined,
      error: null,
    } as never,
    editing: false,
    onStartEdit: vi.fn(),
    onCancelEdit: vi.fn(),
    ...overrides,
  };
}

function setClipboard(writeText?: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: writeText ? { writeText } : undefined,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  setClipboard();
});

describe("AccountRow inactive accounts and IBAN copying", () => {
  it("keeps an inactive account's controls fully opaque", () => {
    render(
      <AccountRow {...props({ account: { ...account, is_active: false } })} />,
    );

    const row = screen
      .getByRole("button", { name: "Aktywuj konto Rachunek główny" })
      .closest("div.rounded-lg");
    expect(row).not.toHaveClass("opacity-60");
    expect(
      screen.getByRole("button", { name: "Aktywuj konto Rachunek główny" }),
    ).toHaveClass("btn-secondary");
  });

  it("announces a successful IBAN copy", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);
    render(<AccountRow {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Numer rachunku został skopiowany.",
      ),
    );
    expect(writeText).toHaveBeenCalledWith(account.iban);
  });

  it("offers the IBAN for manual copying when clipboard access is denied", async () => {
    setClipboard(() =>
      Promise.reject(new DOMException("Denied", "NotAllowedError")),
    );
    render(<AccountRow {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Nie udało się skopiować numeru rachunku. Skopiuj go ręcznie.",
      ),
    );
    expect(
      screen.getByLabelText("Numer rachunku do ręcznego skopiowania"),
    ).toHaveValue(account.iban);
    expect(screen.getByRole("button", { name: "Ukryj" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ukryj" }));

    expect(
      screen.queryByLabelText("Numer rachunku do ręcznego skopiowania"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("offers the IBAN for manual copying when the clipboard is unavailable", async () => {
    setClipboard();
    render(<AccountRow {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Nie udało się skopiować numeru rachunku. Skopiuj go ręcznie.",
      ),
    );
    expect(
      screen.getByLabelText("Numer rachunku do ręcznego skopiowania"),
    ).toHaveValue(account.iban);
    expect(screen.getByRole("button", { name: "Ukryj" })).toBeInTheDocument();
  });

  it("does not restore a manual-copy fallback after it is explicitly hidden", async () => {
    let rejectCopy: (reason?: unknown) => void = () => undefined;
    setClipboard(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectCopy = reject;
        }),
    );
    render(<AccountRow {...props()} />);

    fireEvent.click(screen.getByRole("button", { name: "Pokaż" }));
    fireEvent.click(screen.getByRole("button", { name: "Kopiuj" }));
    fireEvent.click(screen.getByRole("button", { name: "Ukryj" }));

    await act(async () => {
      rejectCopy(new DOMException("Denied", "NotAllowedError"));
    });

    expect(screen.getByRole("button", { name: "Pokaż" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Numer rachunku do ręcznego skopiowania"),
    ).not.toBeInTheDocument();
  });
});
