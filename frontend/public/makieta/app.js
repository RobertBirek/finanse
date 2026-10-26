/* Throwaway UX prototype. In-memory fictional data only; no API or persistence. */
"use strict";
const icons = {
  wallet:
    '<path d="M20 8V5a2 2 0 0 0-2-2H5a3 3 0 0 0 0 6h15v11H5a3 3 0 0 1-3-3V6"/><path d="M20 12h-5v5h5"/>',
  home: '<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
  inbox: '<path d="M4 4h16l2 11v5H2v-5Z"/><path d="M2 15h6l2 3h4l2-3h6"/>',
  folder: '<path d="M3 6h7l2 3h9v11H3Z"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h.01m4 0h.01m4 0h.01"/>',
  spark:
    '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7Z"/>',
  document: '<path d="M5 3h9l5 5v13H5Z"/><path d="M14 3v6h5M9 13h6m-6 4h6"/>',
  settings:
    '<path d="m9 3 6 0 1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z"/><circle cx="12" cy="12" r="3"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  up: '<path d="M12 19V5m-5 5 5-5 5 5"/>',
  down: '<path d="M12 5v14m-5-5 5 5 5-5"/>',
  transfer: '<path d="M3 8h16m-4-4 4 4-4 4M21 16H5m4-4-4 4 4 4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  moon: '<path d="M20 14A9 9 0 0 1 10 4a9 9 0 1 0 10 10Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
  trend: '<path d="m3 17 6-6 4 3 8-10m-6 0h6v6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.01"/>',
  edit: '<path d="m15 4 5 5-11 11H4v-5Zm-2 2 5 5"/>',
  cart: '<path d="M2 3h3l3 12h11l3-9H6m4 15h.01m8 0h.01"/>',
  coffee:
    '<path d="M4 9h13v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5Zm13 1h2a3 3 0 0 1 0 6h-2M8 3v3m5-3v3"/>',
  car: '<path d="m4 9 2-5h12l2 5v10h-3v-3H7v3H4Zm0 1h16M7 13h.01M17 13h.01"/>',
  branch:
    '<path d="M6 3v12a4 4 0 0 0 4 4h8M6 8h12"/><path d="m15 5 3 3-3 3m0 5 3 3-3 3"/>',
};
function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.wallet}</svg>`;
}
function esc(value) {
  return String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
}
const money = (n) =>
  new Intl.NumberFormat("pl-PL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n / 100);
const price = (n) => `${money(n)} zł`;
const signed = (n) => `${n < 0 ? "−" : n > 0 ? "+" : ""}${price(Math.abs(n))}`;
const accounts = [
  {
    id: "velo",
    name: "Konto osobiste",
    bank: "VeloBank",
    mark: "V",
    class: "velo",
    currency: "PLN",
    balance: 864036,
    budget: true,
    iban: "PL00 0000 0000 0000 0000 0000 0000",
    owner: "Alex Kowalski",
    type: "Rachunek osobisty",
    bic: "DEMOXXXX",
  },
  {
    id: "revolut",
    name: "Na co dzień",
    bank: "Revolut",
    mark: "R",
    class: "revolut",
    currency: "PLN",
    balance: 212000,
    budget: true,
    iban: "PL00 0000 0000 0000 0000 0000 0000",
    owner: "Alex Kowalski",
    type: "Rachunek osobisty",
    bic: "DEMOXXXX",
  },
  {
    id: "savings",
    name: "Poduszka finansowa",
    bank: "VeloBank",
    mark: "↗",
    class: "savings",
    currency: "PLN",
    balance: 1350000,
    budget: false,
    iban: "PL00 0000 0000 0000 0000 0000 0000",
    owner: "Alex Kowalski",
    type: "Konto oszczędnościowe",
    bic: "DEMOXXXX",
  },
  {
    id: "cash",
    name: "Portfel",
    bank: "Gotówka",
    mark: "◫",
    class: "cash",
    currency: "PLN",
    balance: 32000,
    budget: true,
    iban: "",
    owner: "Alex Kowalski",
    type: "Gotówka",
    bic: "",
  },
];
const categories = [
  { id: "home", name: "Dom", parent: null, type: "expense", icon: "home" },
  {
    id: "rent",
    name: "Czynsz i najem",
    parent: "home",
    type: "expense",
    icon: "home",
  },
  {
    id: "utilities",
    name: "Media",
    parent: "home",
    type: "expense",
    icon: "home",
  },
  {
    id: "electricity",
    name: "Prąd",
    parent: "utilities",
    type: "expense",
    icon: "spark",
  },
  {
    id: "gas",
    name: "Gaz",
    parent: "utilities",
    type: "expense",
    icon: "home",
  },
  {
    id: "internet",
    name: "Internet",
    parent: "utilities",
    type: "expense",
    icon: "document",
  },
  { id: "food", name: "Jedzenie", parent: null, type: "expense", icon: "cart" },
  {
    id: "groceries",
    name: "Zakupy spożywcze",
    parent: "food",
    type: "expense",
    icon: "cart",
  },
  {
    id: "restaurants",
    name: "Restauracje i kawiarnie",
    parent: "food",
    type: "expense",
    icon: "coffee",
  },
  {
    id: "transport",
    name: "Transport",
    parent: null,
    type: "expense",
    icon: "car",
  },
  {
    id: "car",
    name: "Samochód",
    parent: "transport",
    type: "expense",
    icon: "car",
  },
  { id: "fuel", name: "Paliwo", parent: "car", type: "expense", icon: "car" },
  {
    id: "service",
    name: "Serwis i naprawy",
    parent: "car",
    type: "expense",
    icon: "car",
  },
  {
    id: "public",
    name: "Komunikacja i taxi",
    parent: "transport",
    type: "expense",
    icon: "transfer",
  },
  {
    id: "lifestyle",
    name: "Czas wolny",
    parent: null,
    type: "expense",
    icon: "coffee",
  },
  {
    id: "subscriptions",
    name: "Subskrypcje",
    parent: "lifestyle",
    type: "expense",
    icon: "document",
  },
  {
    id: "shopping",
    name: "Zakupy osobiste",
    parent: null,
    type: "expense",
    icon: "wallet",
  },
  {
    id: "clothes",
    name: "Ubrania",
    parent: "shopping",
    type: "expense",
    icon: "wallet",
  },
  { id: "income", name: "Praca", parent: null, type: "income", icon: "folder" },
  {
    id: "salary",
    name: "Wynagrodzenie",
    parent: "income",
    type: "income",
    icon: "wallet",
  },
  {
    id: "freelance",
    name: "Zlecenia dodatkowe",
    parent: "income",
    type: "income",
    icon: "folder",
  },
];
const transactions = [
  {
    id: "t1",
    name: "Biedronka",
    amount: -18642,
    category: "groceries",
    account: "velo",
    date: "2026-10-26",
    mark: "B",
    tone: "green",
    note: "Zakupy na tydzień",
  },
  {
    id: "t2",
    name: "Spotify",
    amount: -2399,
    category: "subscriptions",
    account: "revolut",
    date: "2026-10-26",
    mark: "S",
    tone: "green",
    note: "Plan Individual",
  },
  {
    id: "t3",
    name: "ORLEN",
    amount: -24780,
    category: "fuel",
    account: "velo",
    date: "2026-10-25",
    mark: "O",
    tone: "red",
  },
  {
    id: "t4",
    name: "Pyszne.pl",
    amount: -6850,
    category: "restaurants",
    account: "revolut",
    date: "2026-10-25",
    mark: "P",
    tone: "red",
  },
  {
    id: "t5",
    name: "Na poduszkę finansową",
    amount: -150000,
    category: null,
    account: "velo",
    destination: "savings",
    date: "2026-10-24",
    icon: "transfer",
    tone: "blue",
    type: "transfer",
  },
  {
    id: "t6",
    name: "Netflix",
    amount: -4900,
    category: "subscriptions",
    account: "revolut",
    date: "2026-10-23",
    mark: "N",
    tone: "red",
  },
  {
    id: "t7",
    name: "Lidl",
    amount: -12783,
    category: "groceries",
    account: "velo",
    date: "2026-10-22",
    mark: "L",
    tone: "blue",
  },
  {
    id: "t8",
    name: "PGE",
    amount: -21876,
    category: "electricity",
    account: "velo",
    date: "2026-10-20",
    icon: "spark",
    tone: "blue",
  },
  {
    id: "t9",
    name: "Kawiarnia Sąsiedzka",
    amount: -14800,
    category: "restaurants",
    account: "revolut",
    date: "2026-10-18",
    icon: "coffee",
    tone: "purple",
  },
  {
    id: "t10",
    name: "Zara",
    amount: -25900,
    category: "clothes",
    account: "velo",
    date: "2026-10-17",
    mark: "Z",
  },
  {
    id: "t11",
    name: "Wynagrodzenie",
    amount: 1250000,
    category: "salary",
    account: "velo",
    date: "2026-10-10",
    icon: "down",
    tone: "green",
    note: "Październik 2026",
  },
  {
    id: "t12",
    name: "Opłata za mieszkanie",
    amount: -230000,
    category: "rent",
    account: "velo",
    date: "2026-10-08",
    icon: "home",
    tone: "blue",
  },
  {
    id: "t13",
    name: "Orange",
    amount: -7900,
    category: "internet",
    account: "velo",
    date: "2026-10-05",
    mark: "O",
    tone: "red",
  },
  {
    id: "t14",
    name: "Uber",
    amount: -3480,
    category: "public",
    account: "revolut",
    date: "2026-10-04",
    mark: "U",
  },
  {
    id: "t15",
    name: "Zakupy spożywcze",
    amount: -32470,
    category: "groceries",
    account: "velo",
    date: "2026-10-03",
    icon: "cart",
    tone: "green",
  },
  {
    id: "t16",
    name: "Restauracja Zielona",
    amount: -19700,
    category: "restaurants",
    account: "revolut",
    date: "2026-10-02",
    icon: "coffee",
    tone: "green",
  },
];
const budgets = [
  { id: "food", limit: 120000, tone: "" },
  { id: "home", limit: 300000, tone: "green" },
  { id: "transport", limit: 70000, tone: "orange" },
  { id: "lifestyle", limit: 25000, tone: "" },
  { id: "shopping", limit: 50000, tone: "green" },
];
const upcoming = [
  {
    name: "Internet · Orange",
    day: "28",
    month: "paź",
    amount: 7900,
    category: "Dom → Media → Internet",
    account: "Konto osobiste",
  },
  {
    name: "Czynsz i najem",
    day: "02",
    month: "lis",
    amount: 230000,
    category: "Dom → Czynsz i najem",
    account: "Konto osobiste",
  },
  {
    name: "Energia elektryczna",
    day: "05",
    month: "lis",
    amount: 22000,
    category: "Dom → Media → Prąd",
    account: "Konto osobiste",
  },
  {
    name: "Wynagrodzenie",
    day: "10",
    month: "lis",
    amount: -1250000,
    category: "Praca → Wynagrodzenie",
    account: "Konto osobiste",
  },
];
const state = {
  view: "overview",
  settingsTab: "accounts",
  categoryType: "expense",
  expanded: new Set(["home", "utilities", "food", "transport"]),
  query: "",
  account: "all",
  type: "all",
  category: "all",
  dark: false,
  accountScope: "all",
};
let nextId = 100,
  toastTimer;
const main = document.getElementById("main"),
  dialog = document.getElementById("detail-dialog");
const account = (id) => accounts.find((a) => a.id === id),
  cat = (id) => categories.find((c) => c.id === id);
function categoryPath(id) {
  const parts = [],
    seen = new Set();
  while (id && !seen.has(id)) {
    seen.add(id);
    const c = cat(id);
    if (!c) break;
    parts.unshift(c.name);
    id = c.parent;
  }
  return parts.join(" → ");
}
function inCategory(id, root) {
  const seen = new Set();
  while (id && !seen.has(id)) {
    if (id === root) return true;
    seen.add(id);
    id = cat(id)?.parent;
  }
  return false;
}
function spent(id) {
  return transactions
    .filter(
      (t) =>
        t.amount < 0 && t.type !== "transfer" && inCategory(t.category, id),
    )
    .reduce((n, t) => n - t.amount, 0);
}
function monthTotals() {
  return transactions.reduce(
    (v, t) => {
      if (t.type === "transfer") return v;
      if (t.amount > 0) v.income += t.amount;
      else v.expense -= t.amount;
      return v;
    },
    { income: 0, expense: 0 },
  );
}
function bankMark(a) {
  return `<span class="bank-mark bank-${a.class}">${esc(a.mark)}</span>`;
}
function merchant(t) {
  return `<span class="merchant ${t.tone || ""}">${t.icon ? icon(t.icon) : esc(t.mark || t.name.slice(0, 1))}</span>`;
}
function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 4400);
}
function nav() {
  const entries = [
    ["home", "Dzisiaj", "demo"],
    ["inbox", "Skrzynka", "demo"],
    ["folder", "Projekty", "demo"],
    ["calendar", "Kalendarz", "demo"],
    ["wallet", "Finanse", "overview"],
    ["spark", "Doradca", "demo"],
    ["document", "Dokumenty", "demo"],
  ];
  document.getElementById("primary-nav").innerHTML =
    entries
      .map(
        ([i, label, view]) =>
          `<button class="nav-item ${view === "overview" && state.view !== "settings" ? "active" : ""}" ${view === "demo" ? `data-demo="${label}"` : `data-view="${view}"`} ${view === "overview" && state.view !== "settings" ? 'aria-current="page"' : ""} aria-label="${label}">${icon(i)}<span>${label}</span></button>`,
      )
      .join("") +
    `<div class="nav-separator"></div><button class="nav-item ${state.view === "settings" ? "active" : ""}" data-view="settings" ${state.view === "settings" ? 'aria-current="page"' : ""} aria-label="Ustawienia">${icon("settings")}<span>Ustawienia</span></button>`;
  document.getElementById("mobile-nav").innerHTML = [
    ["wallet", "Przegląd", "overview"],
    ["transfer", "Transakcje", "transactions"],
    ["calendar", "Nadchodzące", "upcoming"],
    ["trend", "Budżet", "budgets"],
    ["settings", "Ustawienia", "settings"],
  ]
    .map(
      ([i, label, view]) =>
        `<button data-view="${view}" class="${state.view === view ? "active" : ""}" ${state.view === view ? 'aria-current="page"' : ""}>${icon(i)}<span>${label}</span></button>`,
    )
    .join("");
  document.getElementById("private-icon").innerHTML = icon("lock");
  document.getElementById("theme-toggle").innerHTML = icon(
    state.dark ? "sun" : "moon",
  );
  document
    .getElementById("theme-toggle")
    .setAttribute(
      "aria-label",
      state.dark ? "Włącz jasny motyw" : "Włącz ciemny motyw",
    );
  document.getElementById("breadcrumb").textContent =
    state.view === "settings" ? "Ustawienia" : "Finanse";
}
function tabs() {
  return `<nav class="finance-tabs" aria-label="Widoki finansów">${[
    ["overview", "Przegląd"],
    ["transactions", "Transakcje"],
    ["budgets", "Budżet"],
    ["upcoming", "Nadchodzące"],
    ["reports", "Raporty"],
  ]
    .map(
      ([id, label]) =>
        `<button class="tab ${state.view === id ? "active" : ""}" data-view="${id}" ${state.view === id ? 'aria-current="page"' : ""}>${label}</button>`,
    )
    .join("")}</nav>`;
}
function heading(title, subtitle, action = "transaction") {
  return `<div class="page-header"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="header-actions">${state.view !== "settings" ? `<button class="button date-button" data-action="period">${icon("calendar")} Październik 2026 ${icon("chevronDown")}</button>` : ""}${action === "transaction" ? `<button class="button primary" data-action="new-transaction">${icon("plus")} Dodaj transakcję</button>` : ""}</div></div>`;
}
function runway() {
  return `<section class="panel runway-panel" aria-label="Prognoza płynności"><div class="runway-heading"><span class="eyebrow">Do następnej wypłaty · 10 lis</span>${icon("trend")}</div><h2 class="number">${price(552136)}</h2><p>Prognozowane saldo kont budżetowych po zaplanowanych opłatach.</p><svg class="runway-chart" viewBox="0 0 320 77" preserveAspectRatio="none" role="img" aria-label="Przykładowy przebieg prognozowanego salda do 10 listopada"><path class="grid" d="M0 15h320M0 42h320M0 69h320"/><path class="baseline" d="M0 66h320"/><path class="forecast" d="M0 10H30L50 13H90L112 38H155L178 48H220L245 56H298L318 61"/><circle cx="318" cy="61" r="3" fill="#bcd0ff"/></svg><div class="runway-labels"><span>Dzisiaj</span><span>2 lis</span><span>10 lis</span></div><div class="runway-footer"><span>Orientacyjnie dziennie<br /><strong class="number">${price(36809)}</strong></span><button class="text-button" data-action="forecast">Zobacz założenia ${icon("arrow")}</button></div></section>`;
}
function transactionRow(t, table = false) {
  const a = account(t.account),
    transfer = t.type === "transfer";
  return `<button class="transaction-row ${table ? "table-row" : ""}" data-transaction="${t.id}" aria-label="Szczegóły: ${esc(t.name)}, ${signed(t.amount)}">${merchant(t)}<span><span class="transaction-name">${esc(t.name)}</span><span class="transaction-meta">${transfer ? `${esc(a?.name)} → ${esc(account(t.destination)?.name)}` : esc(table ? `${categoryPath(t.category)} · ${a?.bank}` : `${cat(t.category)?.name || "Bez kategorii"} · ${a?.bank}`)}</span></span>${table ? `<span class="table-category"><span class="category-pill">${transfer ? "Transfer własny" : esc(cat(t.category)?.name || "Bez kategorii")}</span></span><span class="table-account">${esc(a?.name || "—")}</span>` : ""}<span class="transaction-amount number ${t.amount > 0 ? "positive" : ""}">${signed(t.amount)}${transfer ? "<small>Bez wpływu na wydatki</small>" : ""}</span></button>`;
}
function groupedTransactions(items, table = false) {
  let date = "";
  return items
    .map((t) => {
      const label =
        t.date === "2026-10-26"
          ? "Dzisiaj · 26 października"
          : t.date === "2026-10-25"
            ? "Wczoraj · 25 października"
            : `${Number(t.date.slice(8))} października`;
      const dateHtml =
        t.date !== date ? `<div class="list-date">${label}</div>` : "";
      date = t.date;
      return dateHtml + transactionRow(t, table);
    })
    .join("");
}
function budgetItem(b, full = false) {
  const amount = spent(b.id),
    percent = Math.min(100, Math.round((amount / b.limit) * 100)),
    step = Math.round(percent / 5) * 5;
  return `<div class="${full ? "budget-full-row" : "budget-item"}">${full ? `<button data-budget-category="${b.id}" aria-label="Pokaż transakcje: ${esc(cat(b.id).name)}">` : ""}<div class="budget-item-head"><span><i class="budget-dot ${b.tone}"></i>${esc(cat(b.id).name)}</span><strong class="number">${price(amount)}</strong></div><div class="progress-track" role="meter" aria-label="Wykorzystanie budżetu: ${esc(cat(b.id).name)}" aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill ${b.tone} p${step}"></div></div><div class="progress-meta"><span>${percent}% wykorzystane</span><span>z ${price(b.limit)}</span></div>${full ? "</button>" : ""}</div>`;
}
function renderOverview() {
  const totals = monthTotals(),
    visibleAccounts =
      state.accountScope === "budget"
        ? accounts.filter((a) => a.budget)
        : accounts,
    balance = visibleAccounts.reduce((n, a) => n + a.balance, 0);
  return (
    heading(
      "Twoje finanse",
      "Wszystko na swoim miejscu. Poniedziałek, 26 października.",
    ) +
    tabs() +
    `<div class="overview-grid"><section class="panel balance-panel"><div class="balance-top"><div><p class="eyebrow">${state.accountScope === "all" ? "Łączne saldo kont" : "Saldo kont budżetowych"}</p><div class="balance-amount number">${money(balance)} <span>PLN</span></div></div><div class="account-toggle" aria-label="Zakres salda"><button data-scope="all" class="${state.accountScope === "all" ? "selected" : ""}" aria-pressed="${state.accountScope === "all"}">Wszystkie</button><button data-scope="budget" class="${state.accountScope === "budget" ? "selected" : ""}" aria-pressed="${state.accountScope === "budget"}">Budżetowe</button></div></div><p class="balance-caption">${icon("info")} ${visibleAccounts.length} konta · saldo na dziś, nie wynik miesiąca</p><div class="quick-actions"><button class="button primary" data-action="new-transaction" data-kind="expense">${icon("plus")} Wydatek</button><button class="button" data-action="new-transaction" data-kind="income">${icon("down")} Przychód</button><button class="button" data-action="new-transaction" data-kind="transfer">${icon("transfer")} Transfer</button></div><div class="balance-divider"></div><div class="period-totals"><div class="period-total"><span class="round-icon">${icon("down")}</span><span><small>Przychody w październiku</small><strong class="number">${price(totals.income)}</strong></span></div><div class="period-total"><span class="round-icon expense">${icon("up")}</span><span><small>Wydatki w październiku</small><strong class="number">${price(totals.expense)}</strong></span></div></div></section>${runway()}</div><div class="accounts-strip" aria-label="Twoje konta">${accounts.map((a) => `<button class="account-chip" data-account-view="${a.id}">${bankMark(a)}<span><small>${esc(a.bank)} · ${esc(a.name)}</small><strong class="number">${price(a.balance)}</strong></span></button>`).join("")}</div><div class="lower-grid"><section class="panel transactions-panel"><div class="panel-header"><div><h2>Ostatnie transakcje</h2><p>Twoja codzienność w jednym miejscu</p></div><button class="text-button" data-view="transactions">Wszystkie ${icon("arrow")}</button></div><div class="transaction-list">${groupedTransactions(transactions.slice(0, 5))}</div></section><section class="panel"><div class="panel-header"><div><h2>Budżet na październik</h2><p>Kontrolujesz, na co wydajesz</p></div><button class="icon-button" data-view="budgets" aria-label="Otwórz budżet">${icon("arrow")}</button></div>${budgets
      .slice(0, 3)
      .map((b) => budgetItem(b))
      .join(
        "",
      )}<div class="budget-bottom"><span>Pozostało w całym budżecie<strong class="number">${price(budgets.reduce((n, b) => n + b.limit - spent(b.id), 0))}</strong></span><button class="text-button" data-settings="limits">Limity ${icon("arrow")}</button></div></section></div>`
  );
}
function filteredTransactions() {
  return transactions.filter((t) => {
    const text = [
      t.name,
      categoryPath(t.category),
      account(t.account)?.name,
      account(t.account)?.bank,
    ]
      .join(" ")
      .toLocaleLowerCase("pl");
    const matchesQuery = text.includes(state.query.toLocaleLowerCase("pl"));
    const matchesAccount =
      state.account === "all" ||
      t.account === state.account ||
      t.destination === state.account;
    const matchesCategory =
      state.category === "all" || inCategory(t.category, state.category);
    const matchesType =
      state.type === "all" ||
      (state.type === "transfer"
        ? t.type === "transfer"
        : t.type !== "transfer" &&
          (state.type === "income" ? t.amount > 0 : t.amount < 0));
    return matchesQuery && matchesAccount && matchesCategory && matchesType;
  });
}
function renderTransactions() {
  return (
    heading(
      "Transakcje",
      "Przeszukuj historię. Sprawdzaj szczegóły. Miej porządek.",
    ) +
    tabs() +
    `<div class="filter-bar"><label class="search-box">${icon("search")}<input id="transaction-search" type="search" placeholder="Szukaj nazwy, kategorii lub banku…" aria-label="Szukaj transakcji" value="${esc(state.query)}" /></label><select class="filter-select" id="account-filter" aria-label="Filtruj po koncie"><option value="all">Wszystkie konta</option>${accounts.map((a) => `<option value="${a.id}" ${state.account === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select><select class="filter-select" id="type-filter" aria-label="Filtruj po rodzaju">${[
      ["all", "Wszystkie rodzaje"],
      ["expense", "Wydatki"],
      ["income", "Przychody"],
      ["transfer", "Transfery"],
    ]
      .map(
        ([id, label]) =>
          `<option value="${id}" ${state.type === id ? "selected" : ""}>${label}</option>`,
      )
      .join(
        "",
      )}</select><button class="button" data-action="filter-category">${icon("branch")} ${state.category === "all" ? "Kategoria" : esc(cat(state.category)?.name || "Kategoria")}</button></div><section class="panel"><div class="panel-header"><h2>Historia operacji</h2><button class="text-button" data-action="clear-filters">Wyczyść filtry</button></div><div id="transaction-results">${transactionResults()}</div></section>`
  );
}
function transactionResults() {
  const items = filteredTransactions(),
    income = items
      .filter((t) => t.amount > 0 && t.type !== "transfer")
      .reduce((n, t) => n + t.amount, 0),
    expense = items
      .filter((t) => t.amount < 0 && t.type !== "transfer")
      .reduce((n, t) => n - t.amount, 0);
  return `<p class="filter-count" role="status">${items.length} operacji · październik 2026</p><div class="transaction-table-head"><span>Transakcja</span><span>Kategoria</span><span class="account-col">Konto</span><span>Kwota</span></div>${items.length ? groupedTransactions(items, true) : '<div class="empty-state"><p>Brak transakcji spełniających te warunki.</p><button class="button" data-action="clear-filters">Wyczyść filtry</button></div>'}<div class="transactions-summary"><div><small>Przychody w wynikach</small><strong class="number positive">${price(income)}</strong></div><div><small>Wydatki w wynikach</small><strong class="number">${price(expense)}</strong></div><div><small>Wynik bez transferów</small><strong class="number">${price(income - expense)}</strong></div></div>`;
}
function renderBudgets() {
  const total = budgets.reduce((n, b) => n + b.limit, 0),
    used = budgets.reduce((n, b) => n + spent(b.id), 0);
  return (
    heading("Budżet", "Plan wydatków, który łatwo sprawdzić.", false) +
    tabs() +
    `<div class="budgets-grid"><section class="panel"><div class="panel-header"><div><h2>Wydatki według kategorii</h2><p>Kliknij kategorię, aby zobaczyć jej transakcje</p></div><button class="text-button" data-settings="limits">Zmień limity ${icon("arrow")}</button></div>${budgets.map((b) => budgetItem(b, true)).join("")}</section><div><section class="panel"><p class="eyebrow">Pozostało do wydania z planu</p><div class="budget-total number">${price(total - used)}</div><p class="muted">Wydano ${price(used)} z ${price(total)}.</p><div class="tree-hint">${icon("info")}<span>To pozostały limit wydatków, nie saldo bankowe ani prognoza dostępnych pieniędzy.</span></div></section><section class="panel"><h2>Warto wiedzieć</h2><div class="insight"><strong>Dom w ramach planu</strong><p>Opłaty za mieszkanie i media mieszczą się w ustalonym limicie.</p></div><div class="insight"><strong>Każdy wydatek liczymy raz</strong><p>Budżet rodzica obejmuje także wszystkie jego podkategorie. Transfery własne nie są wydatkiem.</p></div></section></div></div>`
  );
}
function renderUpcoming() {
  return (
    heading(
      "Nadchodzące",
      "Zaplanowane płatności i wpływy. Bez niespodzianek.",
      false,
    ) +
    tabs() +
    `<div class="budgets-grid"><section class="panel"><div class="panel-header"><h2>Najbliższe 15 dni</h2><button class="text-button" data-settings="schedules">Harmonogramy ${icon("arrow")}</button></div>${upcoming.map((u, i) => `<div class="upcoming-row"><span class="upcoming-date"><strong>${u.day}</strong><small>${u.month}</small></span><span class="upcoming-info"><strong>${u.name}</strong><small>${u.account} · ${u.category}</small></span><span class="number ${u.amount < 0 ? "positive" : ""}">${signed(-u.amount)}</span><button class="button compact desktop-only" data-upcoming="${i}">Szczegóły</button></div>`).join("")}<p class="upcoming-notice">Pozycje planowane nie są wykonanymi transakcjami. Makieta nie księguje płatności.</p></section>${runway()}</div>`
  );
}
function renderReports() {
  const totals = monthTotals();
  return (
    heading("Raporty", "Zrozum, dokąd trafiają Twoje pieniądze.", false) +
    tabs() +
    `<div class="budgets-grid"><section class="panel"><div class="panel-header"><div><h2>Przychody i wydatki</h2><p>Ostatnie sześć miesięcy · dane przykładowe</p></div></div><div class="report-bars" role="img" aria-label="Przykładowe porównanie przychodów i wydatków od maja do października">${["Maj", "Cze", "Lip", "Sie", "Wrz", "Paź"].map((m, i) => `<div class="bar-group"><div class="bar b${[65, 80, 70, 90, 75, 95][i]}"></div><div class="bar out b${[45, 55, 50, 60, 40, 35][i]}"></div><small>${m}</small></div>`).join("")}</div><div class="legend"><span><i></i>Przychody</span><span><i class="out"></i>Wydatki</span></div><div class="transactions-summary"><div><small>Przychody w październiku</small><strong class="number positive">${price(totals.income)}</strong></div><div><small>Wydatki w październiku</small><strong class="number">${price(totals.expense)}</strong></div></div></section><section class="panel"><div class="panel-header"><div><h2>Na co wydajesz</h2><p>Październik · kliknij, aby sprawdzić</p></div></div>${budgets.map((b) => `<div class="budget-full-row"><button data-budget-category="${b.id}"><div class="budget-item-head"><span>${esc(cat(b.id).name)}</span><strong class="number">${price(spent(b.id))} ${icon("chevron")}</strong></div></button></div>`).join("")}<div class="tree-hint">${icon("info")}<span>Transfery między Twoimi kontami są wyłączone z przychodów i wydatków.</span></div></section></div>`
  );
}
function settingsTabs() {
  return `<nav class="settings-nav" aria-label="Ustawienia finansów"><small>FINANSE</small>${[
    ["accounts", "Konta i rachunki"],
    ["categories", "Kategorie"],
    ["limits", "Limity budżetu"],
    ["schedules", "Harmonogramy"],
    ["rules", "Reguły"],
    ["forecast", "Prognoza"],
    ["imports", "Import i integracje"],
  ]
    .map(
      ([id, label]) =>
        `<button class="tab ${state.settingsTab === id ? "active" : ""}" data-settings="${id}" ${state.settingsTab === id ? 'aria-current="page"' : ""}>${label}</button>`,
    )
    .join("")}</nav>`;
}
function settingsAccounts() {
  return `<section class="panel"><div class="settings-title-row"><div><h2>Konta i rachunki</h2><p class="settings-intro">Dane kont, ich rola w budżecie i dane bankowe.</p></div><button class="button primary compact" data-action="new-account">${icon("plus")} Dodaj konto</button></div>${accounts.map((a) => `<div class="settings-account">${bankMark(a)}<div class="settings-account-info"><strong>${esc(a.name)}</strong><span class="badge ${a.budget ? "" : "neutral"}">${a.budget ? "Budżetowe" : "Poza budżetem"}</span><p>${esc(a.bank)} · ${esc(a.currency)} · ${esc(a.type)}</p><p>${a.iban ? "PL•• •••• •••• •••• •••• •••• 0000" : "Brak numeru rachunku · gotówka"}</p></div><button class="button compact" data-edit-account="${a.id}">${icon("edit")} Edytuj</button></div>`).join("")}<div class="tree-hint">${icon("lock")}<span>W makiecie numery rachunków są celowo nieprawidłowe. Nie wpisuj rzeczywistych danych. Konta z historią docelowo archiwizujemy, zamiast usuwać ich operacje.</span></div></section>`;
}
function treeNodes(parent = null) {
  return categories
    .filter((c) => c.parent === parent && c.type === state.categoryType)
    .map((c) => {
      const children = categories.filter((x) => x.parent === c.id),
        expanded = state.expanded.has(c.id);
      return `<div class="tree-node"><div class="tree-row">${children.length ? `<button class="tree-toggle" data-toggle-category="${c.id}" aria-expanded="${expanded}" aria-label="${expanded ? "Zwiń" : "Rozwiń"} ${esc(c.name)}">${icon("chevron")}</button>` : '<span class="tree-spacer"></span>'}<span class="tree-icon">${icon(c.icon)}</span><span class="tree-label">${esc(c.name)}</span>${children.length ? `<small>${children.length} podkategorie</small>` : ""}<span class="tree-actions"><button data-add-category="${c.id}" aria-label="Dodaj podkategorię do ${esc(c.name)}">${icon("plus")}</button><button data-edit-category="${c.id}" aria-label="Edytuj kategorię ${esc(c.name)}">${icon("edit")}</button></span></div>${children.length && expanded ? `<div class="tree-children">${treeNodes(c.id)}</div>` : ""}</div>`;
    })
    .join("");
}
function settingsCategories() {
  return `<section class="panel"><div class="settings-title-row"><div><h2>Drzewo kategorii</h2><p class="settings-intro">Jeden porządek w transakcjach, budżecie i raportach.</p></div><button class="button primary compact" data-action="new-category">${icon("plus")} Dodaj kategorię</button></div><div class="category-toolbar"><div class="segmented" aria-label="Typ kategorii"><button data-category-type="expense" class="${state.categoryType === "expense" ? "active" : ""}" aria-pressed="${state.categoryType === "expense"}">Wydatki</button><button data-category-type="income" class="${state.categoryType === "income" ? "active" : ""}" aria-pressed="${state.categoryType === "income"}">Przychody</button></div><button class="button compact subtle" data-action="expand-tree">Rozwiń wszystko</button><button class="button compact subtle" data-action="collapse-tree">Zwiń</button></div><div id="category-tree">${treeNodes()}</div><div class="tree-hint">${icon("branch")}<span>Dodaj podkategorię przyciskiem +. W edycji zmienisz nazwę i kategorię nadrzędną. Przykład: <strong>Dom → Media → Prąd</strong>. Raporty sumują całą gałąź, bez podwójnego liczenia.</span></div></section>`;
}
function settingsLimits() {
  return `<section class="panel"><div class="panel-header"><div><h2>Limity budżetu</h2><p>Ustal plan. Wykorzystanie sprawdzisz w zakładce Budżet.</p></div></div>${budgets.map((b) => `<div class="settings-rule"><span><strong>${esc(cat(b.id).name)}</strong><p>Limit miesięczny · obejmuje podkategorie</p></span><button class="button compact" data-edit-limit="${b.id}">${price(b.limit)} ${icon("edit")}</button></div>`).join("")}<div class="tree-hint">${icon("info")}<span>Kwota limitu to plan wydatków, a nie pieniądze przeniesione na osobne konto.</span></div></section>`;
}
function settingsSchedules() {
  return `<section class="panel"><div class="panel-header"><div><h2>Harmonogramy</h2><p>Definicje powtarzających się wpływów i opłat.</p></div></div>${upcoming.map((u, i) => `<div class="settings-rule"><span><strong>${u.name}</strong><p>Co miesiąc · ${u.category}</p></span><button class="button compact" data-upcoming="${i}">${price(Math.abs(u.amount))} ${icon("chevron")}</button></div>`).join("")}<div class="tree-hint">${icon("calendar")}<span>Lista terminów jest w Finansach → Nadchodzące. Sam harmonogram nie tworzy wykonanej transakcji.</span></div></section>`;
}
function settingsRules() {
  return `<section class="panel"><h2>Reguły kategoryzacji</h2><p class="settings-intro">Kierunek docelowy: powtarzalne operacje porządkują się same.</p><div class="settings-rule"><span><strong>Nazwa zawiera „Biedronka”</strong><p>Przypisz: Jedzenie → Zakupy spożywcze</p></span><span class="badge neutral">Przykład</span></div><div class="settings-rule"><span><strong>Nazwa zawiera „Spotify”</strong><p>Przypisz: Czas wolny → Subskrypcje</p></span><span class="badge neutral">Przykład</span></div><div class="dialog-note">Reguły to propozycja przyszłej funkcji. Makieta nie wykonuje automatycznej kategoryzacji.</div></section>`;
}
function settingsForecast() {
  return `<section class="panel"><h2>Parametry prognozy</h2><p class="settings-intro">Założenia oddzielone od codziennego podglądu płynności.</p><form id="forecast-form"><div class="form-grid"><div class="form-field"><label for="payday">Dzień wypłaty</label><input id="payday" type="number" min="1" max="31" value="10" required /></div><div class="form-field"><label for="horizon">Horyzont prognozy (dni)</label><input id="horizon" type="number" min="1" max="365" value="30" required /></div></div><div class="form-field"><label for="payday-account">Konto wypłaty</label><select id="payday-account">${accounts.map((a) => `<option>${esc(a.name)}</option>`).join("")}</select></div><button class="button primary" type="submit">Sprawdź zapis demonstracyjny</button></form><div class="dialog-note">Ten formularz pokazuje układ ustawień. Zapis nie zmienia przykładowej prognozy.</div></section>`;
}
function settingsImports() {
  return `<section class="panel"><h2>Import i integracje</h2><p class="settings-intro">Konfiguracja źródeł. Oddzielona od przeglądania pieniędzy.</p><div class="settings-rule"><span><strong>Plik bankowy CSV / PDF</strong><p>Docelowo: podgląd → dopasowanie → zatwierdzenie.</p></span><span class="badge neutral">Koncepcja</span></div><div class="settings-rule"><span><strong>Actual Budget</strong><p>Docelowo: mapowanie kont i kategorii, kontrola sald.</p></span><span class="badge neutral">Koncepcja</span></div><div class="dialog-note">Ta makieta nie przyjmuje plików i nie łączy się z bankiem, Actual ani API aplikacji.</div></section>`;
}
function renderSettings() {
  const content = {
    accounts: settingsAccounts,
    categories: settingsCategories,
    limits: settingsLimits,
    schedules: settingsSchedules,
    rules: settingsRules,
    forecast: settingsForecast,
    imports: settingsImports,
  };
  return (
    heading(
      "Ustawienia",
      "Konfiguracja w jednym miejscu. Spokojna codzienność w finansach.",
      false,
    ) +
    `<div class="settings-layout">${settingsTabs()}<div>${(content[state.settingsTab] || settingsAccounts)()}</div></div>`
  );
}
function render() {
  nav();
  const views = {
    overview: renderOverview,
    transactions: renderTransactions,
    budgets: renderBudgets,
    upcoming: renderUpcoming,
    reports: renderReports,
    settings: renderSettings,
  };
  main.innerHTML = (views[state.view] || renderOverview)();
}
function go(view, settingsTab) {
  if (dialog.open) dialog.close();
  if (settingsTab) state.settingsTab = settingsTab;
  state.view = view;
  const hash = view === "settings" ? `settings/${state.settingsTab}` : view;
  if (location.hash.slice(1) !== hash) history.pushState(null, "", `#${hash}`);
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
}
function route() {
  const [view, tab] = location.hash.slice(1).split("/");
  state.view = [
    "overview",
    "transactions",
    "budgets",
    "upcoming",
    "reports",
    "settings",
  ].includes(view)
    ? view
    : "overview";
  if (
    [
      "accounts",
      "categories",
      "limits",
      "schedules",
      "rules",
      "forecast",
      "imports",
    ].includes(tab)
  )
    state.settingsTab = tab;
  render();
}
function openDialog(title, content) {
  document.getElementById("dialog-content").innerHTML =
    `<div class="dialog-header"><h2 id="detail-title">${title}</h2><button class="icon-button" data-action="close-dialog" aria-label="Zamknij panel">${icon("close")}</button></div><div class="dialog-body">${content}</div>`;
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}
function selectOptions(items, value, includeEmpty) {
  return (
    (includeEmpty ? '<option value="">Bez kategorii nadrzędnej</option>' : "") +
    items
      .map(
        ([id, label]) =>
          `<option value="${esc(id)}" ${id === value ? "selected" : ""}>${esc(label)}</option>`,
      )
      .join("")
  );
}
function showTransaction(id) {
  const t = transactions.find((x) => x.id === id);
  if (!t) return;
  const a = account(t.account);
  openDialog(
    "Szczegóły transakcji",
    `<div class="detail-hero">${merchant(t)}<h3>${esc(t.name)}</h3><div class="amount number ${t.amount > 0 ? "positive" : ""}">${signed(t.amount)}</div><p>${new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long", year: "numeric" }).format(new Date(t.date + "T12:00:00"))} · ${t.type === "transfer" ? "Transfer własny" : "Zaksięgowana · przykład"}</p></div><dl class="detail-fields"><div><dt>Konto</dt><dd>${esc(a.name)} · ${esc(a.bank)}</dd></div>${t.type === "transfer" ? `<div><dt>Na konto</dt><dd>${esc(account(t.destination)?.name)}</dd></div>` : `<div><dt>Kategoria</dt><dd>${esc(categoryPath(t.category))}</dd></div>`}<div><dt>Waluta operacji</dt><dd>PLN</dd></div><div><dt>Opis</dt><dd>${esc(t.note || "Brak dodatkowego opisu")}</dd></div><div><dt>Źródło</dt><dd>Dane demonstracyjne</dd></div></dl>${t.type !== "transfer" ? `<button class="button form-submit" data-recategorize="${t.id}">${icon("branch")} Zmień kategorię</button>` : ""}<div class="dialog-note">${t.type === "transfer" ? "Przeniesienie między własnymi kontami nie zwiększa przychodów ani wydatków." : "Szczegóły są zawsze pod ręką. Nie tracisz filtrów ani miejsca na liście."}</div>`,
  );
}
function showAccount(id) {
  const a = account(id);
  openDialog(
    "Szczegóły konta",
    `<div class="detail-hero">${bankMark(a)}<h3>${esc(a.name)}</h3><div class="amount number">${price(a.balance)}</div><p>${esc(a.bank)} · ${a.currency}</p></div><dl class="detail-fields"><div><dt>Rodzaj konta</dt><dd>${esc(a.type)}</dd></div><div><dt>Budżet</dt><dd>${a.budget ? "Uwzględnione" : "Poza budżetem"}</dd></div><div><dt>Właściciel</dt><dd>${esc(a.owner)}</dd></div>${a.iban ? '<div><dt>Numer rachunku</dt><dd id="account-number">PL•• •••• •••• •••• •••• •••• 0000</dd></div>' : ""}</dl>${a.iban ? `<button class="text-button" data-reveal-account="${a.id}">Pokaż fikcyjny numer rachunku</button>` : ""}<div class="quick-actions"><button class="button primary" data-account-transactions="${a.id}">Historia transakcji ${icon("arrow")}</button><button class="button" data-account-settings="${a.id}">${icon("settings")} Ustawienia</button></div><div class="dialog-note">To konto demonstracyjne. Widoczny numer nie jest prawidłowym rachunkiem bankowym.</div>`,
  );
}
function transactionForm(kind = "expense") {
  openDialog(
    kind === "transfer"
      ? "Zapisz transfer własny"
      : kind === "income"
        ? "Dodaj przychód"
        : "Dodaj wydatek",
    `<form id="transaction-form" data-kind="${kind}"><div class="form-field"><label for="tx-name">${kind === "transfer" ? "Opis transferu" : "Nazwa / odbiorca"}</label><input id="tx-name" name="name" placeholder="${kind === "transfer" ? "Np. Na oszczędności" : "Np. Zakupy spożywcze"}" maxlength="100" required /></div><div class="form-grid"><div class="form-field"><label for="tx-amount">Kwota (PLN)</label><input id="tx-amount" name="amount" type="number" min="0.01" max="1000000" step="0.01" inputmode="decimal" placeholder="0,00" required /></div><div class="form-field"><label for="tx-date">Data</label><input id="tx-date" name="date" type="date" value="2026-10-26" min="2026-10-01" max="2026-10-31" required /></div></div><div class="form-field"><label for="tx-account">${kind === "transfer" ? "Z konta" : "Konto"}</label><select id="tx-account" name="account">${selectOptions(
      accounts.map((a) => [a.id, `${a.name} · ${a.bank}`]),
      "velo",
    )}</select></div>${
      kind === "transfer"
        ? `<div class="form-field"><label for="tx-destination">Na konto</label><select id="tx-destination" name="destination">${selectOptions(
            accounts.map((a) => [a.id, `${a.name} · ${a.bank}`]),
            "savings",
          )}</select></div>`
        : `<div class="form-field"><label for="tx-category">Kategoria</label><select id="tx-category" name="category">${selectOptions(
            categories
              .filter(
                (c) => c.type === (kind === "income" ? "income" : "expense"),
              )
              .map((c) => [c.id, categoryPath(c.id)]),
            kind === "income" ? "salary" : "groceries",
          )}</select></div>`
    }<button type="submit" class="button primary form-submit">Dodaj do makiety</button><div class="dialog-note">Tylko fikcyjne dane. Operacja pojawi się w makiecie do odświeżenia strony. Przykładowa prognoza pozostaje stała.</div></form>`,
  );
}
function editAccount(id) {
  const a = account(id);
  openDialog(
    a ? "Edytuj konto" : "Nowe konto",
    `<form id="account-form" data-id="${a?.id || ""}"><div class="form-field"><label for="acc-name">Nazwa konta</label><input id="acc-name" name="name" value="${esc(a?.name || "")}" placeholder="Np. Konto osobiste" maxlength="80" required /></div><div class="form-grid"><div class="form-field"><label for="acc-bank">Bank / instytucja</label><input id="acc-bank" name="bank" value="${esc(a?.bank || "")}" maxlength="80" placeholder="Np. VeloBank" required /></div><div class="form-field"><label for="acc-type">Rodzaj</label><select id="acc-type" name="type">${selectOptions(
      [
        "Rachunek osobisty",
        "Konto oszczędnościowe",
        "Karta kredytowa",
        "Gotówka",
      ].map((t) => [t, t]),
      a?.type || "Rachunek osobisty",
    )}</select></div></div><div class="form-field"><label for="acc-owner">Właściciel rachunku</label><input id="acc-owner" name="owner" value="${esc(a?.owner || "Alex Kowalski")}" maxlength="80" required /></div><div class="form-field"><label for="acc-iban">Numer rachunku / IBAN</label><input id="acc-iban" name="iban" value="${esc(a?.iban || "")}" placeholder="PL00 0000 0000 0000 0000 0000 0000" maxlength="42" /><small>Wyłącznie fikcyjny numer. Docelowo: walidacja NRB i IBAN.</small></div><div class="form-grid"><div class="form-field"><label for="acc-bic">BIC / SWIFT</label><input id="acc-bic" name="bic" value="${esc(a?.bic || "")}" maxlength="11" placeholder="DEMOXXXX" /></div><div class="form-field"><label for="acc-currency">Waluta</label><select id="acc-currency" name="currency"><option>PLN</option></select><small>Makieta pokazuje konta w PLN.</small></div></div><label class="checkbox-label"><input type="checkbox" name="budget" ${a?.budget !== false ? "checked" : ""} /> Uwzględniaj w budżecie</label><button class="button primary form-submit" type="submit">Zapisz w makiecie</button><div class="dialog-note">Nic nie trafia do serwera ani pamięci przeglądarki. Nie wpisuj prawdziwych danych.</div></form>`,
  );
}
function editCategory(id, parent) {
  const c = cat(id),
    type = c?.type || cat(parent)?.type || state.categoryType,
    selectedParent = c?.parent || parent || "",
    eligible = categories.filter(
      (x) => x.type === type && (!c || !inCategory(x.id, c.id)),
    );
  openDialog(
    c ? "Edytuj kategorię" : parent ? "Nowa podkategoria" : "Nowa kategoria",
    `<form id="category-form" data-id="${c?.id || ""}" data-type="${type}"><div class="form-field"><label for="cat-name">Nazwa kategorii</label><input id="cat-name" name="name" value="${esc(c?.name || "")}" placeholder="Np. Ubezpieczenie mieszkania" maxlength="80" required /></div><div class="form-field"><label for="cat-parent">Kategoria nadrzędna</label><select id="cat-parent" name="parent">${selectOptions(
      eligible.map((x) => [x.id, categoryPath(x.id)]),
      selectedParent,
      true,
    )}</select><small>Wybrany rodzic określa miejsce w drzewie. Nie można przenieść kategorii pod własnego potomka.</small></div><div class="form-field"><label for="cat-type">Typ</label><input id="cat-type" value="${type === "income" ? "Przychód" : "Wydatek"}" disabled /></div><button class="button primary form-submit" type="submit">${c ? "Zapisz zmiany" : "Dodaj kategorię"}</button><div class="dialog-note">Zmiana działa w tej sesji makiety. Nie modyfikuje istniejących kategorii aplikacji.</div></form>`,
  );
}
function categoryPicker(transactionId) {
  const t = transactions.find((x) => x.id === transactionId);
  openDialog(
    transactionId ? "Zmień kategorię" : "Filtruj według kategorii",
    `<form id="category-picker" data-transaction="${transactionId || ""}"><div class="form-field"><label for="pick-category">Kategoria i jej podkategorie</label><select id="pick-category" name="category">${transactionId ? "" : '<option value="all">Wszystkie kategorie</option>'}${selectOptions(
      categories
        .filter((c) =>
          transactionId
            ? c.type === (t.amount > 0 ? "income" : "expense")
            : true,
        )
        .map((c) => [c.id, categoryPath(c.id)]),
      transactionId ? t.category : state.category,
    )}</select></div><button class="button primary form-submit" type="submit">${transactionId ? "Zapisz kategorię w makiecie" : "Zastosuj filtr"}</button></form>`,
  );
}
document.addEventListener("click", (e) => {
  const el = e.target.closest("button,a");
  if (!el) return;
  if (el.dataset.view) {
    go(el.dataset.view);
    return;
  }
  if (el.dataset.settings) {
    go("settings", el.dataset.settings);
    return;
  }
  if (el.dataset.demo) {
    toast(
      `„${el.dataset.demo}” jest poza zakresem tej makiety. Przejdź do Finansów lub Ustawień.`,
    );
    return;
  }
  if (el.id === "theme-toggle") {
    state.dark = !state.dark;
    document.body.classList.toggle("dark", state.dark);
    nav();
    return;
  }
  if (el.dataset.scope) {
    state.accountScope = el.dataset.scope;
    render();
    return;
  }
  if (el.dataset.transaction) {
    showTransaction(el.dataset.transaction);
    return;
  }
  if (el.dataset.accountView) {
    showAccount(el.dataset.accountView);
    return;
  }
  if (el.dataset.editAccount) {
    editAccount(el.dataset.editAccount);
    return;
  }
  if (el.dataset.accountTransactions) {
    dialog.close();
    state.account = el.dataset.accountTransactions;
    state.query = "";
    state.type = "all";
    state.category = "all";
    go("transactions");
    return;
  }
  if (el.dataset.accountSettings) {
    dialog.close();
    go("settings", "accounts");
    editAccount(el.dataset.accountSettings);
    return;
  }
  if (el.dataset.revealAccount) {
    document.getElementById("account-number").textContent = account(
      el.dataset.revealAccount,
    ).iban;
    el.textContent = "Numer demonstracyjny · nie używaj do przelewów";
    el.disabled = true;
    return;
  }
  if (el.dataset.toggleCategory) {
    const id = el.dataset.toggleCategory;
    state.expanded.has(id) ? state.expanded.delete(id) : state.expanded.add(id);
    render();
    document.querySelector(`[data-toggle-category="${id}"]`)?.focus();
    return;
  }
  if (el.dataset.addCategory) {
    editCategory(null, el.dataset.addCategory);
    return;
  }
  if (el.dataset.editCategory) {
    editCategory(el.dataset.editCategory);
    return;
  }
  if (el.dataset.categoryType) {
    state.categoryType = el.dataset.categoryType;
    render();
    return;
  }
  if (el.dataset.budgetCategory) {
    state.category = el.dataset.budgetCategory;
    state.account = "all";
    state.type = "expense";
    state.query = "";
    go("transactions");
    return;
  }
  if (el.dataset.recategorize) {
    categoryPicker(el.dataset.recategorize);
    return;
  }
  if (el.dataset.editLimit) {
    const b = budgets.find((x) => x.id === el.dataset.editLimit);
    openDialog(
      "Zmień limit budżetu",
      `<form id="limit-form" data-category="${b.id}"><div class="form-field"><label for="limit-amount">${esc(cat(b.id).name)} · limit miesięczny (PLN)</label><input id="limit-amount" name="amount" type="number" min="0.01" max="1000000" step="0.01" value="${b.limit / 100}" required /></div><button class="button primary form-submit" type="submit">Zapisz limit w makiecie</button><div class="dialog-note">Limit obejmuje całą gałąź. Zmiana jest widoczna w Budżecie do odświeżenia.</div></form>`,
    );
    return;
  }
  if (el.dataset.upcoming !== undefined) {
    const u = upcoming[Number(el.dataset.upcoming)];
    openDialog(
      "Planowana operacja",
      `<div class="detail-hero"><h3>${u.name}</h3><div class="amount number">${signed(-u.amount)}</div><p>Planowany termin: ${u.day} ${u.month} 2026</p></div><dl class="detail-fields"><div><dt>Kategoria</dt><dd>${u.category}</dd></div><div><dt>Konto</dt><dd>${u.account}</dd></div><div><dt>Częstotliwość</dt><dd>Co miesiąc</dd></div></dl><div class="dialog-note">To plan, nie potwierdzona płatność. Makieta nie tworzy z niego transakcji.</div>`,
    );
    return;
  }
  switch (el.dataset.action) {
    case "close-dialog":
      dialog.close();
      break;
    case "new-transaction":
      transactionForm(el.dataset.kind || "expense");
      break;
    case "new-account":
      editAccount();
      break;
    case "new-category":
      editCategory();
      break;
    case "expand-tree":
      categories.forEach((c) => state.expanded.add(c.id));
      render();
      break;
    case "collapse-tree":
      state.expanded.clear();
      render();
      break;
    case "filter-category":
      categoryPicker();
      break;
    case "clear-filters":
      state.query = "";
      state.account = "all";
      state.type = "all";
      state.category = "all";
      render();
      break;
    case "period":
      toast(
        "Makieta pokazuje październik 2026. W docelowym interfejsie tutaj wybierzesz dowolny okres.",
      );
      break;
    case "forecast":
      openDialog(
        "Założenia prognozy",
        `<h3>Prognoza jest osobna od salda</h3><dl class="detail-fields"><div><dt>Saldo kont budżetowych</dt><dd>${price(1108036)}</dd></div><div><dt>Zaplanowane opłaty</dt><dd>− ${price(259900)}</dd></div><div><dt>Rezerwa na zmienne wydatki</dt><dd>− ${price(296000)}</dd></div><div><dt>Saldo przed wypłatą</dt><dd>${price(552136)}</dd></div><div><dt>Dni do wypłaty</dt><dd>15</dd></div></dl><div class="dialog-note">Stały scenariusz demonstracyjny. Kwoty prognozy nie przeliczają się po zmianach w makiecie. Konto oszczędnościowe jest poza budżetem. Docelowo obliczenia wykonuje backend.</div><button class="button form-submit" data-settings="forecast">Parametry prognozy ${icon("arrow")}</button>`,
      );
      break;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "transaction-search") {
    state.query = e.target.value;
    document.getElementById("transaction-results").innerHTML =
      transactionResults();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "account-filter" || e.target.id === "type-filter") {
    state[e.target.id === "account-filter" ? "account" : "type"] =
      e.target.value;
    document.getElementById("transaction-results").innerHTML =
      transactionResults();
  }
});
document.addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target,
    fd = new FormData(form);
  if (form.id === "transaction-form") {
    const kind = form.dataset.kind,
      amount = Math.round(Number(fd.get("amount")) * 100),
      source = fd.get("account"),
      destination = fd.get("destination");
    if (!amount || amount < 0) return;
    if (kind === "transfer" && source === destination) {
      toast("Wybierz dwa różne konta.");
      return;
    }
    const t = {
      id: `demo${nextId++}`,
      name: String(fd.get("name")).trim(),
      amount: kind === "income" ? amount : -amount,
      category: kind === "transfer" ? null : fd.get("category"),
      account: source,
      date: fd.get("date"),
      icon:
        kind === "transfer"
          ? "transfer"
          : kind === "income"
            ? "down"
            : "wallet",
      tone: kind === "income" ? "green" : "blue",
      type: kind,
    };
    if (!t.name) return;
    if (kind === "transfer") {
      t.destination = destination;
      account(destination).balance += amount;
    }
    account(source).balance += t.amount;
    transactions.unshift(t);
    transactions.sort((a, b) => b.date.localeCompare(a.date));
    state.query = "";
    state.account = "all";
    state.type = "all";
    state.category = "all";
    dialog.close();
    go("transactions");
    toast("Transakcja dodana tylko do makiety.");
  } else if (form.id === "account-form") {
    const data = {
      name: String(fd.get("name")).trim(),
      bank: String(fd.get("bank")).trim(),
      type: fd.get("type"),
      owner: String(fd.get("owner")).trim(),
      iban: String(fd.get("iban")).trim(),
      bic: String(fd.get("bic")).trim(),
      currency: "PLN",
      budget: fd.has("budget"),
    };
    if (!data.name || !data.bank || !data.owner) return;
    const existing = account(form.dataset.id);
    if (existing) Object.assign(existing, data);
    else
      accounts.push({
        ...data,
        id: `account${nextId++}`,
        mark: data.bank.slice(0, 1),
        class: "savings",
        balance: 0,
      });
    dialog.close();
    render();
    toast("Konto zapisane tylko w makiecie.");
  } else if (form.id === "category-form") {
    const id = form.dataset.id,
      name = String(fd.get("name")).trim(),
      parent = fd.get("parent") || null;
    if (!name) return;
    if (id && parent && inCategory(parent, id)) {
      toast("Kategoria nie może być własnym potomkiem.");
      return;
    }
    if (id) Object.assign(cat(id), { name, parent });
    else
      categories.push({
        id: `category${nextId++}`,
        name,
        parent,
        type: form.dataset.type,
        icon: "branch",
      });
    let p = parent;
    while (p) {
      state.expanded.add(p);
      p = cat(p)?.parent;
    }
    dialog.close();
    render();
    toast("Drzewo kategorii zaktualizowane w makiecie.");
  } else if (form.id === "category-picker") {
    const id = form.dataset.transaction;
    if (id) {
      transactions.find((x) => x.id === id).category = fd.get("category");
      dialog.close();
      render();
      toast("Kategoria zmieniona tylko w makiecie.");
    } else {
      state.category = fd.get("category");
      dialog.close();
      render();
    }
  } else if (form.id === "limit-form") {
    const amount = Math.round(Number(fd.get("amount")) * 100);
    if (amount <= 0) return;
    budgets.find((b) => b.id === form.dataset.category).limit = amount;
    dialog.close();
    render();
    toast("Limit budżetu zmieniony tylko w makiecie.");
  } else if (form.id === "forecast-form") {
    toast("Podgląd formularza: przykładowa prognoza pozostaje bez zmian.");
  }
});
dialog.addEventListener("click", (e) => {
  if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      dialog.close();
  }
});
window.addEventListener("popstate", route);
window.addEventListener("hashchange", route);
route();
