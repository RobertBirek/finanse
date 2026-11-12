import type { Category } from "../api/finance";

/** Deliberately unsorted, with active children below archived parents. */
export const categorySelectFixture: Category[] = [
  {
    id: "water",
    name: "Woda",
    parent_id: "home",
    type: "expense",
    is_active: true,
  },
  {
    id: "auto-child",
    name: "Zamek",
    parent_id: "auto",
    type: "expense",
    is_active: true,
  },
  {
    id: "home",
    name: "Dom",
    parent_id: null,
    type: "expense",
    is_active: false,
  },
  {
    id: "gas",
    name: "Gaz",
    parent_id: "home",
    type: "expense",
    is_active: true,
  },
  {
    id: "auto",
    name: "Auto",
    parent_id: null,
    type: "expense",
    is_active: false,
  },
  {
    id: "salary",
    name: "Pensja",
    parent_id: null,
    type: "income",
    is_active: true,
  },
  {
    id: "old",
    name: "Stara",
    parent_id: "home",
    type: "expense",
    is_active: false,
  },
];
