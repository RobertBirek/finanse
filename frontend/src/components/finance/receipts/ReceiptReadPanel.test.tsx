import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { useAuthStore } from "../../../stores/authStore";
import { ReceiptReadPanel } from "./ReceiptReadPanel";
import {
  readContext,
  readJob,
  exportPreview,
  readResult,
  importPreview,
} from "./receiptReadTestData";
beforeEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  useAuthStore.setState({
    sessionVersion: 42,
    user: {
      id: "owner",
      email: "test@example.invalid",
      display_name: "Test",
      is_active: true,
    },
    authStatus: "authenticated",
  });
});
function mount(dirty = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const imported = vi.fn(async () => {}),
    locked = vi.fn();
  const view = render(
    <QueryClientProvider client={client}>
      <ReceiptReadPanel
        billId="bill"
        dirty={dirty}
        disabled={false}
        onImported={imported}
        onImportLockChange={locked}
      />
    </QueryClientProvider>,
  );
  return { ...view, client, imported, locked };
}
function reads(job: unknown = readJob) {
  return vi.spyOn(api, "get").mockImplementation(async (url) => ({
    data: String(url).endsWith("/context")
      ? readContext
      : String(url).endsWith("/result")
        ? readResult
        : String(url).endsWith("/reads")
          ? { items: [job], next_cursor: null }
          : job,
  }));
}
async function consent() {
  await screen.findByRole("option", { name: /Mój paragon/ });
  fireEvent.change(await screen.findByLabelText("Zdjęcie paragonu"), {
    target: { value: "photo" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Odczytaj produkty ze zdjęcia" }),
  );
  return screen.findByRole("button", {
    name: "Wyślij zdjęcie i odczytaj produkty",
  });
}
it("choosing a photo and mounting never automatically exports it", async () => {
  reads();
  const post = vi.spyOn(api, "post");
  mount();
  fireEvent.change(await screen.findByLabelText("Zdjęcie paragonu"), {
    target: { value: "photo" },
  });
  expect(post).not.toHaveBeenCalled();
});
it("unknown_start_replays_exact_body_and_key", async () => {
  reads();
  let attempts = 0;
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("read-export-preview"))
      return { data: exportPreview };
    if (++attempts === 1) throw new Error("Lost");
    return { data: readJob };
  });
  mount();
  const send = await consent();
  expect(screen.getByText(/całego obrazu/)).toBeInTheDocument();
  fireEvent.click(send);
  const replay = await screen.findByRole("button", {
    name: "Sprawdź tę samą próbę",
  });
  fireEvent.click(replay);
  await waitFor(() => expect(attempts).toBe(2));
  const writes = post.mock.calls.filter((c) =>
    String(c[0]).endsWith("read-start"),
  );
  expect(writes[0]).toEqual(writes[1]);
});
it("unknown_status_never_starts_paid_reread", async () => {
  reads({
    ...readJob,
    state: "unknown",
    can_cancel: false,
    poll_after_ms: null,
  });
  const post = vi
    .spyOn(api, "post")
    .mockResolvedValue({ data: { ...exportPreview, reread_of_job_id: "job" } });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /Próba 1/ }));
  await screen.findByText(/Wynik wysłania nieznany/);
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "Sprawdź wynik" }));
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Odczytaj ponownie — możliwy kolejny koszt",
    }),
  );
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  expect(post.mock.calls[0][1]).toMatchObject({ reread_of_job_id: "job" });
});
it("explicit import warns before abandoning local and saved drafts", async () => {
  reads({
    ...readJob,
    state: "succeeded",
    can_cancel: false,
    poll_after_ms: null,
  });
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => ({
    data: String(url).endsWith("read-import-preview") ? importPreview : {},
  }));
  const view = mount(true);
  fireEvent.click(await screen.findByRole("button", { name: /Próba 1/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Użyj w szkicu" }));
  const confirm = await screen.findByRole("button", {
    name: "Zastąp szkic odczytem",
  });
  expect(screen.getByText(/niezapisane/)).toBeInTheDocument();
  expect(view.imported).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  await waitFor(() => expect(view.imported).toHaveBeenCalledOnce());
  expect(
    post.mock.calls.filter(
      (c) =>
        String(c[0]).endsWith("payment-apply") ||
        String(c[0]).endsWith("/approve"),
    ),
  ).toHaveLength(0);
});
it("cancel dispatch conflict shows sent status, never false cancellation", async () => {
  reads();
  const post = vi
    .spyOn(api, "post")
    .mockRejectedValue({ response: { status: 409 } });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /Próba 1/ }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Anuluj niewysłany odczyt" }),
  );
  await screen.findByText(/nie można cofnąć/);
  expect(post).toHaveBeenCalledOnce();
});
it("a replaced session ignores late consent and prevents old writes", async () => {
  reads();
  let resolve!: (v: unknown) => void;
  const post = vi.spyOn(api, "post").mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  mount();
  await screen.findByRole("option", { name: /Mój paragon/ });
  fireEvent.change(await screen.findByLabelText("Zdjęcie paragonu"), {
    target: { value: "photo" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Odczytaj produkty ze zdjęcia" }),
  );
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
    resolve({ data: exportPreview });
  });
  expect(
    screen.queryByRole("button", {
      name: "Wyślij zdjęcie i odczytaj produkty",
    }),
  ).not.toBeInTheDocument();
});

it("unknown start survives unmount and replays the original scoped intent only on demand", async () => {
  reads();
  let attempts = 0;
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("read-export-preview"))
      return { data: exportPreview };
    if (++attempts === 1) throw new Error("Lost");
    return { data: readJob };
  });
  const first = mount();
  fireEvent.click(await consent());
  await screen.findByRole("button", { name: "Sprawdź tę samą próbę" });
  const original = post.mock.calls.find((c) =>
    String(c[0]).endsWith("read-start"),
  );
  first.unmount();
  mount();
  const recover = await screen.findByRole("button", {
    name: "Sprawdź tę samą próbę",
  });
  expect(attempts).toBe(1);
  fireEvent.click(recover);
  await waitFor(() => expect(attempts).toBe(2));
  expect(
    post.mock.calls.filter((c) => String(c[0]).endsWith("read-start"))[1],
  ).toEqual(original);
});

it("unknown import survives remount, freezes parent and cannot install a historical response", async () => {
  reads({
    ...readJob,
    state: "succeeded",
    can_cancel: false,
    poll_after_ms: null,
  });
  let attempts = 0;
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("read-import-preview"))
      return { data: importPreview };
    if (++attempts === 1) throw new Error("Lost");
    return { data: { historical: "must-not-install" } };
  });
  const first = mount(true);
  fireEvent.click(await screen.findByRole("button", { name: /Próba 1/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Użyj w szkicu" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Zastąp szkic odczytem" }),
  );
  await screen.findByRole("button", { name: "Sprawdź tę samą próbę" });
  const original = post.mock.calls.find((c) =>
    String(c[0]).endsWith("read-import"),
  );
  first.unmount();
  const second = mount(true);
  const recover = await screen.findByRole("button", {
    name: "Sprawdź tę samą próbę",
  });
  expect(second.locked).toHaveBeenCalledWith(true);
  expect(attempts).toBe(1);
  fireEvent.click(recover);
  await waitFor(() => expect(second.imported).toHaveBeenCalledOnce());
  expect(
    post.mock.calls.filter((c) => String(c[0]).endsWith("read-import"))[1],
  ).toEqual(original);
});

it("session replacement clears persisted uncertain intent and never resends it", async () => {
  reads();
  const post = vi.spyOn(api, "post").mockImplementation(async (url) => {
    if (String(url).endsWith("read-export-preview"))
      return { data: exportPreview };
    throw new Error("Lost");
  });
  const first = mount();
  fireEvent.click(await consent());
  await screen.findByRole("button", { name: "Sprawdź tę samą próbę" });
  first.unmount();
  await act(async () => {
    useAuthStore.setState({ sessionVersion: 43 });
  });
  mount();
  await screen.findByRole("option", { name: /Mój paragon/ });
  expect(
    screen.queryByRole("button", { name: "Sprawdź tę samą próbę" }),
  ).not.toBeInTheDocument();
  expect(
    post.mock.calls.filter((c) => String(c[0]).endsWith("read-start")),
  ).toHaveLength(1);
});

it("unavailable recovery storage blocks a new command before dispatch", async () => {
  reads();
  const post = vi.spyOn(api, "post").mockResolvedValue({ data: exportPreview });
  mount();
  const send = await consent();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Storage blocked");
  });
  fireEvent.click(send);
  await screen.findByText(/Nie można zachować klucza operacji/);
  expect(
    post.mock.calls.filter((c) => String(c[0]).endsWith("read-start")),
  ).toHaveLength(0);
});
