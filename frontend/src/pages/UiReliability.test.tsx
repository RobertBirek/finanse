import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Today } from "./Today";
import { Settings } from "./Settings";
import { MemoryRouter } from "react-router-dom";
import { Calendar } from "./Calendar";
import { Advisor } from "./Advisor";
import { Dialog } from "../components/Dialog";
import { DocumentList } from "../components/DocumentList";
import { DocumentUpload } from "../components/DocumentUpload";
import { DocumentViewer } from "../components/DocumentViewer";
import { CashflowSettingsForm } from "../components/finance/CashflowSettingsForm";
import type { DocumentData } from "../api/documents";

const mocks = vi.hoisted(() => ({
  conversations: vi.fn(),
  messages: vi.fn(),
  send: vi.fn(),
  confirm: vi.fn(),
  deny: vi.fn(),
  tasks: vi.fn(),
  blocks: vi.fn(),
  summary: vi.fn(),
  docs: vi.fn(),
  text: vi.fn(),
  upload: vi.fn(),
  settings: vi.fn(),
  accounts: vi.fn(),
  mutate: vi.fn(),
  retry: vi.fn(),
}));
vi.mock("../api/advisor", () => ({
  useConversations: mocks.conversations,
  useMessages: mocks.messages,
  useSendMessage: mocks.send,
  useConfirmToolExecution: () => ({ mutate: mocks.confirm }),
  useDenyToolExecution: () => ({ mutate: mocks.deny }),
}));
vi.mock("../stores/authStore", () => ({
  useAuthStore: (selector: (state: unknown) => unknown) =>
    selector({ user: { display_name: "Anna", email: "anna@example.invalid" } }),
}));
vi.mock("../api/work", () => ({
  useTasks: mocks.tasks,
  useTimeBlocks: mocks.blocks,
  useCreateTask: () => ({ mutate: mocks.mutate }),
  useUpdateTask: () => ({ mutate: mocks.mutate }),
}));
vi.mock("../api/finance", () => ({
  useFinancialSummary: mocks.summary,
  useCashflowSettings: mocks.settings,
  useAccounts: mocks.accounts,
  useUpdateCashflowSettings: () => ({ mutate: mocks.mutate }),
}));
vi.mock("../api/documents", async (original) => ({
  ...(await original<typeof import("../api/documents")>()),
  useDocuments: mocks.docs,
  useDocumentText: mocks.text,
  useUploadDocument: mocks.upload,
  useDeleteDocument: () => ({ mutate: mocks.mutate }),
}));

const doc = {
  id: "doc-1",
  original_name: "example.pdf",
  status: "done",
  size_bytes: 100,
  created_at: "2026-10-20T12:00:00Z",
  mime_type: "application/pdf",
} as DocumentData;
const query = (data: unknown) => ({
  data,
  isLoading: false,
  isError: false,
  refetch: mocks.retry,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.conversations.mockReturnValue(
    query([{ id: "conv-1", title: "Rozmowa testowa" }]),
  );
  mocks.messages.mockReturnValue(query([]));
  mocks.send.mockReturnValue({ mutate: mocks.mutate });
  mocks.tasks.mockReturnValue(query([]));
  mocks.blocks.mockReturnValue(query([]));
  mocks.summary.mockReturnValue(
    query({ net_total_pln: 123456, month: 10, year: 2026 }),
  );
  mocks.docs.mockReturnValue(query([doc]));
  mocks.text.mockReturnValue(query({ extracted_text: "Treść" }));
  mocks.upload.mockReturnValue({ mutate: mocks.mutate, isPending: false });
  mocks.settings.mockReturnValue(
    query({
      payday_day: 10,
      payday_account_id: null,
      forecast_horizon_days: 30,
      overdue_grace_days: 3,
    }),
  );
  mocks.accounts.mockReturnValue(query([]));
});

describe("trustworthy query states", () => {
  it("does not turn failed today queries into empty lists or a zero balance", () => {
    const failed = { ...query(undefined), isError: true };
    mocks.tasks.mockReturnValue(failed);
    mocks.blocks.mockReturnValue(failed);
    mocks.summary.mockReturnValue(failed);
    render(<Today />);
    expect(screen.getAllByRole("alert")).toHaveLength(3);
    expect(screen.queryByText("0 PLN")).not.toBeInTheDocument();
    expect(screen.queryByText(/Brak aktywnych zadań/)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getAllByRole("button", { name: "Spróbuj ponownie" })[0],
    );
    expect(mocks.retry).toHaveBeenCalledOnce();
  });
  it("keeps loading distinct from successful emptiness and formats money", () => {
    mocks.tasks.mockReturnValue({ ...query(undefined), isLoading: true });
    render(<Today />);
    expect(screen.getByRole("status")).toHaveTextContent("Ładowanie");
    expect(screen.queryByText(/Brak aktywnych zadań/)).not.toBeInTheDocument();
    expect(screen.getByText(/1.*234,56 PLN/)).toBeInTheDocument();
    expect(
      screen.getByLabelText("Tytuł szybkiego zadania"),
    ).toBeInTheDocument();
  });
  it("reports failed settings before waiting for a form that will never load", () => {
    mocks.settings.mockReturnValue({ ...query(undefined), isError: true });
    render(<CashflowSettingsForm />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Nie udało się pobrać ustawień",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Spróbuj ponownie" }));
    expect(mocks.retry).toHaveBeenCalledTimes(2);
  });
  it("does not offer unsupported preference or autonomy controls", () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText(/nie zmienia uprawnień/)).toBeInTheDocument();
  });
});

describe("document recovery UI", () => {
  it("keeps filters available when their result is empty", () => {
    mocks.docs.mockImplementation((params) =>
      query(params?.status ? [] : [doc]),
    );
    render(<DocumentList />);
    fireEvent.click(screen.getByRole("button", { name: "Oczekuje" }));
    expect(
      screen.getByText("Brak dokumentów o wybranym statusie."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Wszystkie" }));
    expect(
      screen.getByRole("button", { name: "Otwórz dokument: example.pdf" }),
    ).toBeInTheDocument();
  });
  it("does not disguise document errors as no documents", () => {
    mocks.docs.mockReturnValue({ ...query(undefined), isError: true });
    render(<DocumentList />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Nie udało się pobrać dokumentów",
    );
    expect(screen.queryByText(/Brak dokumentów/)).not.toBeInTheDocument();
  });
  it("enables text fetching only when the live document becomes done", () => {
    const { rerender } = render(
      <DocumentViewer
        document={{ ...doc, status: "processing" }}
        onClose={vi.fn()}
      />,
    );
    expect(mocks.text).toHaveBeenLastCalledWith(doc.id, false);
    expect(screen.getByRole("status")).toHaveTextContent("przetwarzany");
    rerender(<DocumentViewer document={doc} onClose={vi.fn()} />);
    expect(mocks.text).toHaveBeenLastCalledWith(doc.id, true);
    expect(screen.getByText("Treść")).toBeInTheDocument();
  });
  it("explains a blank OCR result", () => {
    mocks.text.mockReturnValue(query({ extracted_text: "  \n" }));
    render(<DocumentViewer document={doc} onClose={vi.fn()} />);
    expect(screen.getByText(/Nie znaleziono tekstu/)).toBeInTheDocument();
  });
  it("has an accessible upload action and rejects empty files", () => {
    render(<DocumentUpload />);
    expect(
      screen.getByRole("button", { name: "Wybierz dokument do przesłania" }),
    ).toBeInTheDocument();
    const input = document.querySelector('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File([], "empty.pdf")] } });
    expect(mocks.mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("niepusty plik");
  });
  it("announces duplicate uploads", () => {
    mocks.upload.mockReturnValue({
      isSuccess: true,
      data: { is_duplicate: true },
      mutate: mocks.mutate,
    });
    render(<DocumentUpload />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Ten dokument jest już zapisany",
    );
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("calendar and live local date", () => {
  it("refreshes today's date across local midnight without reloading the app", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 20, 23, 59, 50));
    render(<Today />);
    const first =
      mocks.blocks.mock.calls[mocks.blocks.mock.calls.length - 1]![0]
        .start_time;
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    const second =
      mocks.blocks.mock.calls[mocks.blocks.mock.calls.length - 1]![0]
        .start_time;
    expect(second).not.toBe(first);
    expect(new Date(second).getDate()).toBe(21);
  });
  it("uses explicit UTC boundaries for local calendar ranges and exposes a mobile agenda", () => {
    render(<Calendar />);
    expect(screen.getByRole("region", { name: "Agenda" })).toBeInTheDocument();
    const bounds =
      mocks.blocks.mock.calls[mocks.blocks.mock.calls.length - 1]![0];
    expect(bounds.start_time).toMatch(/Z$/);
    expect(bounds.end_time).toMatch(/Z$/);
    expect(new Date(bounds.start_time).getHours()).toBe(0);
    expect(new Date(bounds.end_time).getHours()).toBe(23);
    expect(
      screen.getByRole("button", { name: "Poprzedni tydzień" }),
    ).toBeInTheDocument();
  });
  it("does not skip February when navigating from January 31", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 31, 12));
    render(<Calendar />);
    fireEvent.click(screen.getByRole("button", { name: "Miesiąc" }));
    fireEvent.click(screen.getByRole("button", { name: "Następny miesiąc" }));
    expect(screen.getByText("Luty 2026")).toBeInTheDocument();
  });
  it("reports calendar failures rather than displaying empty days", () => {
    mocks.blocks.mockReturnValue({ ...query(undefined), isError: true });
    render(<Calendar />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Nie udało się pobrać kalendarza",
    );
    expect(
      screen.queryByRole("region", { name: "Agenda" }),
    ).not.toBeInTheDocument();
  });
});

describe("Advisor mobile and explicit actions", () => {
  it("opens a named history dialog and lets the user start a new conversation", () => {
    render(<Advisor />);
    fireEvent.click(screen.getByRole("button", { name: "Rozmowy" }));
    const dialog = screen.getByRole("dialog", { name: "Rozmowy Doradcy" });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(dialog.querySelector("button.btn-primary")!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Wiadomość do Doradcy")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Wyślij wiadomość" }),
    ).toBeDisabled();
  });
  it("keeps a failed message draft visible and does not resend automatically", () => {
    mocks.send.mockReturnValue({ mutate: mocks.mutate, isError: true });
    render(<Advisor />);
    fireEvent.change(screen.getByLabelText("Wiadomość do Doradcy"), {
      target: { value: "Moje pytanie" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Nie udało się wysłać");
    expect(screen.getByLabelText("Wiadomość do Doradcy")).toHaveValue(
      "Moje pytanie",
    );
    expect(mocks.mutate).not.toHaveBeenCalled();
  });
  it("shows pending confirmation actions without expanding technical details", () => {
    mocks.messages.mockReturnValue(
      query([
        {
          id: "msg-1",
          conversation_id: "conv-1",
          role: "assistant",
          content: "Propozycja",
          tool_executions: [
            {
              id: "exec-1",
              tool_name: "create_task",
              arguments: { title: "Przykład" },
              result: null,
              status: "pending_confirmation",
            },
          ],
        },
      ]),
    );
    render(<Advisor />);
    expect(screen.getByText("Wymaga potwierdzenia")).toBeInTheDocument();
    expect(document.querySelector("details")).not.toHaveAttribute("open");
    expect(mocks.confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
    expect(mocks.confirm).toHaveBeenCalledWith({
      executionId: "exec-1",
      conversationId: "conv-1",
    });
  });
});

describe("native modal lifecycle", () => {
  it("does not close on interaction inside the panel, and blocks cancellation during a save", () => {
    const close = vi.fn();
    const { rerender } = render(
      <Dialog label="Próba" onClose={close} busy>
        <button type="button">Wewnątrz</button>
      </Dialog>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Wewnątrz" }));
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { cancelable: true }),
    );
    expect(close).not.toHaveBeenCalled();
    rerender(
      <Dialog label="Próba" onClose={close}>
        <button type="button">Wewnątrz</button>
      </Dialog>,
    );
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { cancelable: true }),
    );
    expect(close).toHaveBeenCalledOnce();
  });
});
