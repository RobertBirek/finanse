import { describe, expect, it } from "vitest";
import { categoryPath, eligibleCategoryParents } from "./categories";

const categories = [
  {
    id: "home",
    name: "Dom",
    parent_id: null,
    type: "expense",
    is_active: false,
  },
  {
    id: "media",
    name: "Media",
    parent_id: "home",
    type: "expense",
    is_active: true,
  },
  {
    id: "power",
    name: "Prąd",
    parent_id: "media",
    type: "expense",
    is_active: true,
  },
] as const;

describe("category hierarchy", () => {
  it("keeps active grandchildren reachable under an archived parent", () => {
    expect(categoryPath("power", categories)).toBe("Dom → Media → Prąd");
  });
  it("excludes a category and all descendants as reparent targets", () => {
    expect(
      eligibleCategoryParents("home", categories).map((item) => item.id),
    ).toEqual([]);
    expect(
      eligibleCategoryParents("media", categories).map((item) => item.id),
    ).toEqual(["home"]);
  });
});
