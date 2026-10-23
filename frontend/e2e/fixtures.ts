import { expect, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIST =
  process.env.E2E_DIST_DIR ??
  fileURLToPath(new URL("../dist/", import.meta.url));
const stamp = "2026-10-20T08:00:00Z";
export const account = {
  id: "10000000-0000-0000-0000-000000000001",
  name: "Eurokonto",
  type: "checking",
  currency: "EUR",
  is_active: true,
  is_budget_account: true,
  balance_pln: 54321,
  opened_at: "2026-01-01",
  closed_at: null,
};
export const transaction = {
  id: "20000000-0000-0000-0000-000000000001",
  transaction_date: "2026-10-20",
  description: "Zakup kawy",
  type: "expense",
  source: "manual",
  is_pending: false,
  postings: [
    {
      id: "p1",
      account_id: account.id,
      category_id: null,
      source_currency: "EUR",
      source_amount: 12345,
      base_amount_pln: 54321,
      fx_rate: 4.4,
      direction: "debit",
    },
  ],
};

export async function fixtures(
  page: Page,
  options: { todayError?: boolean } = {},
) {
  const unknown: string[] = [],
    mutations: string[] = [],
    errors: string[] = [],
    searches: URLSearchParams[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let confirmed = false;
  const message = () => ({
    id: "m1",
    conversation_id: "c1",
    role: "assistant",
    content: "Propozycja działania",
    created_at: stamp,
    tool_executions: [
      {
        id: "e1",
        tool_name: "create_task",
        arguments: { title: "Sprawdź dokument" },
        result: null,
        status: confirmed ? "completed" : "pending_confirmation",
      },
    ],
  });
  await page.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.origin !== "https://ui.test.invalid") {
      unknown.push(url.origin);
      await route.abort();
      return;
    }
    if (!url.pathname.startsWith("/api/")) {
      const file =
        url.pathname.startsWith("/assets/") ||
        /\.(json|svg|png|ico|ttf)$/.test(url.pathname)
          ? url.pathname.slice(1)
          : "index.html";
      const resolved = path.resolve(DIST, file);
      if (!resolved.startsWith(path.resolve(DIST) + path.sep)) {
        await route.abort();
        return;
      }
      try {
        const body = await fs.readFile(resolved);
        const type = file.endsWith(".js")
          ? "text/javascript"
          : file.endsWith(".css")
            ? "text/css"
            : file.endsWith(".json")
              ? "application/json"
              : file.endsWith(".ttf")
                ? "font/ttf"
                : file.endsWith(".svg")
                  ? "image/svg+xml"
                  : "text/html";
        await route.fulfill({ status: 200, contentType: type, body });
      } catch {
        await route.fulfill({ status: 404, body: "Unknown fixture asset" });
      }
      return;
    }
    let body: unknown,
      status = 200;
    if (request.method() !== "GET") {
      mutations.push(request.method() + " " + url.pathname);
      if (url.pathname === "/api/advisor/tool-executions/e1/confirm") {
        confirmed = true;
        body = message();
      } else {
        unknown.push(request.method() + " " + url.pathname);
        status = 422;
        body = { detail: "Unregistered fixture mutation" };
      }
    } else if (url.pathname === "/api/auth/me")
      body = {
        id: "qa",
        display_name: "Tester UI",
        email: "qa@example.invalid",
      };
    else if (url.pathname === "/api/finance/accounts") body = [account];
    else if (url.pathname === "/api/finance/categories") body = [];
    else if (url.pathname === "/api/finance/transactions/search") {
      searches.push(url.searchParams);
      const offset = Number(url.searchParams.get("offset") ?? 0),
        limit = Number(url.searchParams.get("limit") ?? 25);
      body = {
        items: Array.from(
          { length: Math.min(limit, Math.max(0, 53 - offset)) },
          (_, i) => ({
            ...transaction,
            id: i + offset === 0 ? transaction.id : `tx${offset + i}`,
            description:
              i + offset === 0 ? transaction.description : `Kawa ${offset + i}`,
          }),
        ),
        total: 53,
        offset,
        limit,
      };
    } else if (url.pathname.startsWith("/api/finance/transactions/"))
      body = transaction;
    else if (url.pathname === "/api/finance/summary") {
      status = options.todayError ? 503 : 200;
      body = options.todayError
        ? { detail: "Fixture unavailable" }
        : {
            accounts: [],
            income_total_pln: 10000,
            expense_total_pln: 1000,
            net_total_pln: 9000,
            month: 10,
            year: 2026,
          };
    } else if (
      [
        "/api/work/tasks",
        "/api/work/time-blocks",
        "/api/work/projects",
      ].includes(url.pathname)
    ) {
      status = options.todayError ? 503 : 200;
      body = options.todayError ? { detail: "Fixture unavailable" } : [];
    } else if (url.pathname === "/api/documents")
      body =
        !url.searchParams.get("status") ||
        url.searchParams.get("status") === "done"
          ? [
              {
                id: "d1",
                original_name: "Faktura.pdf",
                status: "done",
                mime_type: "application/pdf",
                size_bytes: 1234,
                created_at: stamp,
              },
            ]
          : [];
    else if (url.pathname === "/api/documents/d1/text")
      body = { extracted_text: "Tekst testowego dokumentu" };
    else if (url.pathname === "/api/advisor/conversations")
      body = [
        {
          id: "c1",
          title: "Rozmowa testowa",
          created_at: stamp,
          updated_at: stamp,
        },
      ];
    else if (url.pathname === "/api/advisor/conversations/c1/messages")
      body = [message()];
    else {
      unknown.push(url.pathname);
      status = 500;
      body = { detail: "Unknown fixture API" };
    }
    await route.fulfill({ status, json: body });
  });
  return {
    searches,
    mutations,
    assertClean: () => {
      expect(unknown).toEqual([]);
      expect(errors).toEqual([]);
    },
  };
}
