import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { FinanceImportReview } from "./FinanceImportReview";
import {
  batchFixture,
  httpFailure,
  importTestWrapper,
  installImportServer,
  receiptFixture,
  rowFixture,
  setImportActor,
} from "../test/bankImportFixtures";

let server: ReturnType<typeof installImportServer>;
async function prepareButton() {
  const button = await screen.findByRole("button", {
    name: "Przygotuj podgląd",
  });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}
afterEach(() => server?.restore());
function renderReview() {
  const context = importTestWrapper(
    <Routes>
      <Route
        path="/finances/imports/:batchId"
        element={<FinanceImportReview />}
      />
    </Routes>,
    "/finances/imports/batch-a",
  );
  return { ...render(context.node), client: context.client };
}

describe("bank review and frozen confirmation", () => {
  it("refreshes source rows when worker publication changes the batch, without window focus or a reload", async () => {
    let published = false;
    const queued = batchFixture({
      version: 1,
      groups: [],
      sources: [
        {
          ...batchFixture().sources[0],
          current_revision_id: null,
          processing_state: "processing",
          validation_state: "needs_review",
        },
      ],
    });
    server = installImportServer({
      batch: queued,
      onRequest: (request) =>
        request.url.endsWith("/rows")
          ? {
              items: published ? [rowFixture()] : [],
              total: published ? 1 : 0,
              offset: 0,
              limit: 100,
            }
          : undefined,
    });
    const view = renderReview();
    await screen.findByText(/Brak wierszy w tym widoku/);
    published = true;
    server.setBatch(batchFixture({ version: 3, groups: [] }));
    const key = view.client
      .getQueryCache()
      .getAll()
      .find(
        (query) =>
          query.queryKey.length === 5 && query.queryKey[4] === "batch-a",
      )!.queryKey;
    await view.client.refetchQueries({ queryKey: key, exact: true });
    expect(await screen.findByText("Syntetyczny zakup")).toBeVisible();
  });
  it("retries a source parse only after a dedicated source action, without committing rows", async () => {
    server = installImportServer({
      batch: batchFixture({
        sources: [
          {
            ...batchFixture().sources[0],
            processing_state: "error",
            validation_state: "blocked",
          },
        ],
      }),
    });
    renderReview();
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Ponów odczyt: statement.pdf",
      }),
    );
    await waitFor(() =>
      expect(
        server.requests.some((request) =>
          request.url.endsWith("/sources/source-a/prepare"),
        ),
      ).toBe(true),
    );
    expect(
      server.requests.filter((request) => request.url.endsWith("/prepare")),
    ).toHaveLength(1);
    expect(
      server.requests.find((request) => request.url.endsWith("/prepare"))!.key,
    ).toBeTruthy();
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(0);
  });
  it("saves a one-source own transfer to the chosen existing cash account without income or expense postings", async () => {
    server = installImportServer({
      onRequest: (request) =>
        request.url === "/finance/accounts"
          ? [
              {
                id: "account-pln",
                name: "Rachunek",
                type: "checking",
                currency: "PLN",
                is_active: true,
              },
              {
                id: "account-cash",
                name: "Gotówka",
                type: "cash",
                currency: "PLN",
                is_active: true,
              },
            ]
          : undefined,
    });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.change(screen.getByLabelText("Rodzaj operacji"), {
      target: { value: "transfer" },
    });
    await within(screen.getByLabelText("Drugi własny rachunek")).findByRole(
      "option",
      { name: "Gotówka · PLN" },
    );
    fireEvent.change(screen.getByLabelText("Drugi własny rachunek"), {
      target: { value: "account-cash" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz decyzję" }));
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.url.endsWith("/decisions")),
      ).toBe(true),
    );
    expect(
      server.requests.find((request) => request.url.endsWith("/decisions"))!
        .body,
    ).toMatchObject({
      decisions: [
        {
          kind: "transfer",
          account_id: "account-pln",
          other_account_id: "account-cash",
          category_id: null,
        },
      ],
    });
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(0);
  });
  it("shows existing payment facts and requires an explicit date-difference acknowledgement before linking", async () => {
    server = installImportServer({
      onRequest: (request) => {
        if (request.url.endsWith("/candidates"))
          return [
            {
              transaction_id: "old-transaction",
              account_posting_id: "old-posting",
              strength: "possible",
              reasons: ["same_signed_amount"],
              conflicts: ["booking_date_difference"],
            },
          ];
        if (request.url === "/finance/transactions/old-transaction")
          return {
            id: "old-transaction",
            transaction_date: "2026-01-02",
            description: "Stary zakup Actual",
            type: "expense",
            source: "actual",
            is_pending: false,
            project_id: null,
            postings: [
              {
                id: "old-posting",
                transaction_id: "old-transaction",
                account_id: "account-pln",
                category_id: null,
                source_amount: 100,
                source_currency: "PLN",
                base_amount_pln: 100,
                direction: "debit",
              },
            ],
            date_metadata: null,
          };
      },
    });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.change(screen.getByLabelText("Co zrobić z wierszem?"), {
      target: { value: "link" },
    });
    await screen.findByRole("option", { name: /old-transaction/ });
    fireEvent.change(screen.getByLabelText(/Istniejąca operacja/), {
      target: { value: "old-transaction" },
    });
    expect(await screen.findByText("Stary zakup Actual")).toBeVisible();
    expect(screen.getByText(/Data starej operacji: 2026-01-02/)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Zapisz decyzję" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Akceptuję różnicę dat/));
    fireEvent.click(screen.getByRole("button", { name: "Zapisz decyzję" }));
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.url.endsWith("/decisions")),
      ).toBe(true),
    );
    expect(
      server.requests.find((request) => request.url.endsWith("/decisions"))!
        .body,
    ).toMatchObject({
      decisions: [
        {
          action: "link",
          existing_transaction_id: "old-transaction",
          acknowledgements: ["link_date_difference"],
        },
      ],
    });
    expect(
      server.requests.filter(
        (request) =>
          request.method !== "get" &&
          request.url.startsWith("/finance/transactions/"),
      ),
    ).toHaveLength(0);
  });
  it("can recover a receipt even after another read sees a newer committed batch version", async () => {
    server = installImportServer({
      onRequest: (request) => {
        if (request.url.endsWith("/commit"))
          throw new Error("Synthetic uncertain result");
      },
    });
    const view = renderReview();
    fireEvent.click(await prepareButton());
    const panel = await screen.findByRole("region", {
      name: "Podgląd zatwierdzenia",
    });
    fireEvent.click(
      within(panel).getByRole("checkbox", { name: /Potwierdzam/ }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
    );
    await screen.findByText("Synthetic uncertain result");
    server.setBatch(
      batchFixture({ version: 3, commit_state: "committed", groups: [] }),
    );
    await view.client.invalidateQueries({ queryKey: ["finance", "imports"] });
    await waitFor(() =>
      expect(
        within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
      ).toBeDisabled(),
    );
    server.setReceipt(receiptFixture);
    fireEvent.click(
      await screen.findByRole("button", { name: "Sprawdź zapisany wynik" }),
    );
    expect(await screen.findByText(/Zapisano wynik importu/)).toBeVisible();
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(1);
  });
  it("binds an explicit reparse comparison acknowledgement to the shown candidate revision", async () => {
    const batch = batchFixture();
    batch.sources[0] = {
      ...batch.sources[0],
      candidate_revision_id: "revision-candidate",
      candidate_parser_version: "parser-v2",
      validation_state: "needs_review",
    };
    server = installImportServer({ batch });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.click(
      await screen.findByLabelText(
        /Porównałem bieżący wiersz z ponownym odczytem/,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Zapisz decyzję" }));
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.url.endsWith("/decisions")),
      ).toBe(true),
    );
    expect(
      server.requests.find((request) => request.url.endsWith("/decisions"))!
        .body,
    ).toMatchObject({
      decisions: [
        {
          acknowledgements: ["reparse_comparison:source-a:revision-candidate"],
        },
      ],
    });
  });
  it("keeps card-header confirmation separate from immutable bank transaction amounts", async () => {
    const batch = batchFixture();
    batch.sources[0].layout = "velo_card_v1";
    server = installImportServer({
      batch,
      onRequest: (request) =>
        request.url === "/finance/accounts"
          ? [
              {
                id: "account-pln",
                name: "Karta",
                type: "credit_card",
                currency: "PLN",
                is_active: true,
              },
            ]
          : undefined,
    });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.click(
      await screen.findByLabelText("Dodaj osobny rekord wyciągu karty"),
    );
    expect(
      screen.getByRole("button", { name: "Zapisz decyzję" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Co zrobić z wierszem?"), {
      target: { value: "defer" },
    });
    expect(
      screen.getByRole("button", { name: "Zapisz decyzję" }),
    ).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Co zrobić z wierszem?"), {
      target: { value: "create" },
    });
    for (const [label, value] of [
      ["Początek okresu karty", "2026-01-01"],
      ["Koniec okresu karty", "2026-01-31"],
      ["Termin z nagłówka karty", "2026-02-12"],
      ["Dług bieżącego cyklu PLN", "9,00"],
      ["Minimum z nagłówka PLN", "1,00"],
    ])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(
      screen.getByLabelText(/Potwierdzam znaczenie zadłużenia bieżącego cyklu/),
    );
    fireEvent.click(screen.getByRole("button", { name: "Zapisz decyzję" }));
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.url.endsWith("/decisions")),
      ).toBe(true),
    );
    const body = server.requests.find((request) =>
      request.url.endsWith("/decisions"),
    )!.body as { decisions: { card_header: unknown }[] };
    expect(body.decisions[0].card_header).toEqual({
      account_id: "account-pln",
      period_start: "2026-01-01",
      period_end: "2026-01-31",
      due_date: "2026-02-12",
      debt_pln: 900,
      minimum_pln: 100,
      debt_definition_confirmed: true,
    });
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(0);
  });
  it("compares a candidate revision read only without promoting it or changing current rows", async () => {
    const current = batchFixture();
    current.sources[0] = {
      ...current.sources[0],
      candidate_revision_id: "revision-candidate",
      candidate_parser_version: "parser-v2",
      validation_state: "needs_review",
    };
    server = installImportServer({
      batch: current,
      onRequest: (request) =>
        request.url.endsWith("/rows") && request.config.params?.revision_id
          ? {
              items: [
                {
                  ...rowFixture({
                    id: "candidate-row",
                    revision_id: "revision-candidate",
                    decision: null,
                  }),
                  bank_fields: {
                    ...rowFixture().bank_fields!,
                    description: "Wiersz z ponownego odczytu",
                  },
                },
              ],
              total: 1,
              offset: 0,
              limit: 100,
            }
          : undefined,
    });
    renderReview();
    fireEvent.click(
      await screen.findByRole("button", { name: /Porównaj ponowny odczyt/ }),
    );
    expect(await screen.findByText("Wiersz z ponownego odczytu")).toBeVisible();
    expect(
      screen.getByLabelText("Wybierz wiersz Wiersz z ponownego odczytu"),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Przygotuj podgląd" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Wróć do bieżącego odczytu" }),
    );
    expect(await screen.findByText("Syntetyczny zakup")).toBeVisible();
    expect(
      server.requests.filter((request) => request.method !== "get"),
    ).toHaveLength(0);
  });
  it("never offers accounts or categories cached for a previous owner while current mapping loads", async () => {
    server = installImportServer({
      onRequest: (request) =>
        ["/finance/accounts", "/finance/categories"].includes(request.url)
          ? new Promise(() => {})
          : undefined,
    });
    setImportActor("owner-b");
    const context = importTestWrapper(
      <Routes>
        <Route
          path="/finances/imports/:batchId"
          element={<FinanceImportReview />}
        />
      </Routes>,
      "/finances/imports/batch-a",
    );
    context.client.setQueryData(
      ["finance", "accounts"],
      [
        {
          id: "secret-old",
          name: "Prywatny rachunek poprzedniego użytkownika",
          currency: "PLN",
          is_active: true,
          type: "checking",
        },
      ],
    );
    context.client.setQueryData(
      ["finance", "categories"],
      [
        {
          id: "secret-cat",
          name: "Prywatna kategoria",
          is_active: true,
          type: "expense",
        },
      ],
    );
    render(context.node);
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    expect(
      screen.queryByText("Prywatny rachunek poprzedniego użytkownika · PLN"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Prywatna kategoria")).not.toBeInTheDocument();
    context.client.clear();
  });
  it("retains the same commit intent key when receipt lookup is still unresolved", async () => {
    let attempts = 0;
    server = installImportServer({
      onRequest: (request) => {
        if (request.url.endsWith("/commit") && ++attempts === 1)
          throw new Error("Synthetic uncertain result");
      },
    });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.click(await prepareButton());
    const panel = await screen.findByRole("region", {
      name: "Podgląd zatwierdzenia",
    });
    fireEvent.click(
      within(panel).getByRole("checkbox", { name: /Potwierdzam/ }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
    );
    await screen.findByText("Synthetic uncertain result");
    expect(screen.getByLabelText("Rodzaj operacji")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Przygotuj podgląd" }),
    ).toBeDisabled();
    await waitFor(() =>
      expect(
        within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
      ).toBeEnabled(),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
    );
    await screen.findByText(/Zapisano wynik importu/);
    const commits = server.requests.filter((request) =>
      request.url.endsWith("/commit"),
    );
    expect(commits).toHaveLength(2);
    expect(commits[1].key).toBe(commits[0].key);
  });
  it("saves an explicit expense refund classification without changing source facts", async () => {
    server = installImportServer({
      rows: [
        {
          ...rowFixture(),
          bank_fields: {
            ...rowFixture().bank_fields!,
            amount: 100,
            description: "Zwrot zakupu",
          },
        },
      ],
    });
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Zwrot zakupu"),
    );
    fireEvent.change(screen.getByLabelText("Rodzaj operacji"), {
      target: { value: "expense_refund" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz decyzję" }));
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.url.endsWith("/decisions")),
      ).toBe(true),
    );
    const request = server.requests.find((request) =>
      request.url.endsWith("/decisions"),
    )!;
    expect(request.body).toMatchObject({
      expected_version: 2,
      decisions: [{ kind: "expense_refund", row_ids: ["row-a"] }],
    });
    expect(JSON.stringify(request.body)).not.toContain("postings");
    expect(
      server.requests.filter((request) => request.url.endsWith("/commit")),
    ).toHaveLength(0);
  });
  it("blocks an FX decision without its real second source leg", async () => {
    server = installImportServer();
    renderReview();
    fireEvent.click(
      await screen.findByLabelText("Wybierz wiersz Syntetyczny zakup"),
    );
    fireEvent.change(screen.getByLabelText("Rodzaj operacji"), {
      target: { value: "exchange" },
    });
    fireEvent.change(screen.getByLabelText("Drugi własny rachunek"), {
      target: { value: "account-eur" },
    });
    expect(
      screen.getByRole("button", { name: "Zapisz decyzję" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/Wybierz dwa rzeczywiste wiersze wymiany/),
    ).toBeVisible();
  });
  it("restores persisted decisions from the deep link and leaves bank dates read only", async () => {
    server = installImportServer();
    renderReview();
    expect(await screen.findByText("Syntetyczny zakup")).toBeVisible();
    expect(screen.getByText(/2026-01-03/)).toBeVisible();
    expect(screen.getByText(/2026-01-02/)).toBeVisible();
    expect(
      screen.queryByLabelText("Zmień kwotę źródłową"),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Wybierz grupę/)).toBeChecked();
    expect(
      server.requests.some(
        (request) => request.url === "/finance/imports/batch-a",
      ),
    ).toBe(true);
  });
  it("requires explicit confirmation of the frozen preview and sends no postings", async () => {
    server = installImportServer();
    renderReview();
    fireEvent.click(await prepareButton());
    const panel = await screen.findByRole("region", {
      name: "Podgląd zatwierdzenia",
    });
    const commit = within(panel).getByRole("button", {
      name: "Zatwierdź wybrane grupy",
    });
    expect(commit).toBeDisabled();
    fireEvent.click(
      within(panel).getByRole("checkbox", { name: /Potwierdzam/ }),
    );
    fireEvent.click(commit);
    expect(await screen.findByText(/Zapisano wynik importu/)).toBeVisible();
    const request = server.requests.find((request) =>
      request.url.endsWith("/commit"),
    )!;
    expect(request.body).toEqual({
      preview_id: "preview-a",
      request_hash: "b".repeat(64),
    });
  });
  it("distinguishes a blocked source from an acknowledged ledger gap", async () => {
    server = installImportServer({
      batch: batchFixture({
        sources: [
          {
            ...batchFixture().sources[0],
            validation_state: "blocked",
            checks: [
              {
                code: "balance_rollforward",
                required: true,
                result: "failed",
                expected: 900,
                actual: 800,
              },
            ],
          },
        ],
      }),
    });
    renderReview();
    expect(await screen.findByText(/Błąd kontroli źródła/)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Przygotuj podgląd" }),
    ).toBeDisabled();
  });
  it("shows three source currencies separately without claiming a combined balance", async () => {
    const rows = ["PLN", "EUR", "USD"].map((currency, index) => {
      const row = rowFixture({ id: `row-${index}`, decision: null });
      return {
        ...row,
        bank_fields: {
          ...row.bank_fields!,
          currency: currency as "PLN" | "EUR" | "USD",
          description: `Zakup ${currency}`,
        },
      };
    });
    server = installImportServer({ rows, batch: batchFixture({ groups: [] }) });
    renderReview();
    expect(await screen.findByText("Zakup PLN")).toBeVisible();
    expect(screen.getByText("Zakup EUR")).toBeVisible();
    expect(screen.getByText("Zakup USD")).toBeVisible();
    expect(screen.queryByText(/Łączne saldo/)).not.toBeInTheDocument();
  });
  it("recovers a timed out commit by receipt using the same intent", async () => {
    server = installImportServer({
      onRequest: (request) => {
        if (request.url.endsWith("/commit")) {
          server.setReceipt(receiptFixture);
          throw new Error("Synthetic lost response");
        }
        if (request.url.includes("/commands/")) return receiptFixture;
      },
    });
    renderReview();
    fireEvent.click(await prepareButton());
    const panel = await screen.findByRole("region", {
      name: "Podgląd zatwierdzenia",
    });
    fireEvent.click(
      within(panel).getByRole("checkbox", { name: /Potwierdzam/ }),
    );
    fireEvent.click(
      within(panel).getByRole("button", { name: "Zatwierdź wybrane grupy" }),
    );
    expect(await screen.findByText(/Zapisano wynik importu/)).toBeVisible();
    const commits = server.requests.filter((request) =>
      request.url.endsWith("/commit"),
    );
    expect(commits).toHaveLength(1);
    expect(
      server.requests.find((request) => request.url.includes("/commands/"))
        ?.url,
    ).toContain(commits[0].key);
  });
  it("displays server-required gap acknowledgement instead of changing an opening balance", async () => {
    server = installImportServer({
      onRequest: (request) =>
        request.url.endsWith("/preview")
          ? Promise.reject(
              httpFailure(409, {
                code: "import_acknowledgement_required",
                detail: "Wymagane potwierdzenia: opening_gap:source-a",
              }),
            )
          : undefined,
    });
    renderReview();
    fireEvent.click(await prepareButton());
    expect(await screen.findByText(/Różnica salda otwarcia/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Wyrównaj saldo/ }),
    ).not.toBeInTheDocument();
  });
});
