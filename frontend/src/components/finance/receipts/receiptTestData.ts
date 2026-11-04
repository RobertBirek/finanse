import type {
  ReceiptItemsContext,
  ReceiptBody,
  ReceiptPaymentPreview,
} from "../../../api/receiptItems";
export const body: ReceiptBody = {
  store_id: "store",
  store_version: 1,
  lines: [
    {
      line_key: "a",
      name: "Mleko",
      amount_minor: 8000,
      category_id: "food",
      hint: null,
    },
    {
      line_key: "b",
      name: "Płyn",
      amount_minor: 2000,
      category_id: "home",
      hint: null,
    },
  ],
  discounts: [
    {
      discount_key: "d",
      name: "Kupon",
      amount_minor: 1000,
      shares: [
        { line_key: "a", amount_minor: 800 },
        { line_key: "b", amount_minor: 200 },
      ],
    },
  ],
};
export const categories = [
  {
    id: "food",
    name: "Spożywka",
    type: "expense" as const,
    is_active: true,
    parent_id: null,
  },
  {
    id: "home",
    name: "Dom",
    type: "expense" as const,
    is_active: true,
    parent_id: null,
  },
];
export const context = (
  version = 1,
  approved = false,
): ReceiptItemsContext => ({
  bill_id: "bill",
  bill_version: 1,
  state_version: version,
  editable: true,
  blocked_reason: null,
  draft: approved
    ? null
    : {
        id: "draft",
        sequence: version,
        kind: "draft",
        header_sha256: "a".repeat(64),
        body_sha256: "b".repeat(64),
        body,
        created_at: "2026-11-04T12:00:00Z",
        current: true,
        problems: [],
      },
  approved: approved
    ? {
        id: "approved",
        sequence: version,
        kind: "approved",
        header_sha256: "a".repeat(64),
        body_sha256: "b".repeat(64),
        body,
        created_at: "2026-11-04T12:00:00Z",
        current: true,
        problems: [],
      }
    : null,
  calculation: {
    line_nets: [
      { line_key: "a", net_minor: 7200 },
      { line_key: "b", net_minor: 1800 },
    ],
    net_total_minor: 9000,
    difference_minor: 0,
    parts: [
      { category_id: "food", amount_minor: 7200 },
      { category_id: "home", amount_minor: 1800 },
    ],
    problems: [],
  },
  eligible_category_ids: ["food", "home"],
  limits: {
    max_lines: 200,
    max_discounts: 50,
    max_discount_shares: 1000,
    item_name_max_chars: 300,
    store_name_max_chars: 200,
    history_page_size: 5,
    history_prefix_min_chars: 4,
  },
});
export const preview: ReceiptPaymentPreview = {
  expected_state_version: 2,
  approved_revision_id: "approved",
  transaction_id: "txn",
  context_snapshot: "c".repeat(64),
  preview_snapshot: "d".repeat(64),
  before_parts: [{ category_id: "food", amount_minor: 9000 }],
  after_parts: [
    { category_id: "food", amount_minor: 7200 },
    { category_id: "home", amount_minor: 1800 },
  ],
  target_paths: { food: "Spożywka", home: "Dom" },
  line_nets: [
    { line_key: "a", net_minor: 7200 },
    { line_key: "b", net_minor: 1800 },
  ],
  body_sha256: "b".repeat(64),
  total_minor: 9000,
  currency: "PLN",
  notice:
    "Zmieni się tylko podział kategorii. Kwota, konto i daty płatności pozostaną bez zmian.",
};
export const hint = {
  ref: {
    source_bill_id: "source",
    source_revision_id: "source-rev",
    source_line_key: "source-line",
    category_id: "food",
    match_kind: "exact" as const,
    algorithm_version: "receipt-history-v1",
    source_sha256: "e".repeat(64),
  },
  product_name: "Mleko",
  category_path: "Spożywka",
  purchased_on: null,
  approved_at: "2026-11-03T12:00:00Z",
};
