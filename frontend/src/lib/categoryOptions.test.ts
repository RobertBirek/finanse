import { describe, expect, it } from "vitest";
import type { Category } from "../api/finance";
import { categorySelectFixture } from "../test/categoryFixtures";
import { categoryOptions } from "./categories";

describe("sorted full category paths for selects", () => {
  it("sorts by full ancestry rather than the leaf name or API order", () => {
    const options = categoryOptions(categorySelectFixture);
    expect(options.map(({ label }) => label)).toEqual([
      "Auto",
      "Auto - Zamek",
      "Dom",
      "Dom - Gaz",
      "Dom - Stara",
      "Dom - Woda",
      "Pensja",
    ]);
    expect(options.map(({ id }) => id)).toEqual([
      "auto",
      "auto-child",
      "home",
      "gas",
      "old",
      "water",
      "salary",
    ]);
  });

  it("resolves all levels and archived ancestors outside the eligible list", () => {
    const hierarchy: Category[] = [
      ...categorySelectFixture,
      {
        id: "media",
        name: "Media",
        parent_id: "home",
        type: "expense",
        is_active: false,
      },
      {
        id: "power",
        name: "Prąd",
        parent_id: "media",
        type: "expense",
        is_active: true,
      },
    ];
    expect(
      categoryOptions(
        hierarchy.filter(({ id }) => id === "power"),
        hierarchy,
      ),
    ).toEqual([
      expect.objectContaining({
        id: "power",
        name: "Prąd",
        label: "Dom - Media - Prąd",
      }),
    ]);
  });

  it("uses Polish alphabet ordering and ignores case", () => {
    const names = [
      "Życie",
      "łódź",
      "zakupy",
      "Światło",
      "Sport",
      "Łączność",
      "laser",
      "Dom",
      "auto",
    ];
    const input = names.map((name, index) => ({
      id: String(index),
      name,
      parent_id: null,
      type: "expense" as const,
      is_active: true,
    }));
    expect(categoryOptions(input).map(({ label }) => label)).toEqual([
      "auto",
      "Dom",
      "laser",
      "Łączność",
      "łódź",
      "Sport",
      "Światło",
      "zakupy",
      "Życie",
    ]);
  });

  it("disambiguates same leaf names without modifying query data", () => {
    const input = [
      ...categorySelectFixture,
      {
        id: "gas-auto",
        name: "Gaz",
        parent_id: "auto",
        type: "expense" as const,
        is_active: true,
      },
    ];
    const before = structuredClone(input);
    Object.freeze(input);
    input.forEach(Object.freeze);
    const options = categoryOptions(input);
    expect(
      options
        .filter(({ name }) => name === "Gaz")
        .map(({ id, label }) => [id, label]),
    ).toEqual([
      ["gas-auto", "Auto - Gaz"],
      ["gas", "Dom - Gaz"],
    ]);
    expect(input).toEqual(before);
    expect(options).not.toBe(input);
  });

  it("handles missing ancestors and cycles without looping or losing the selected category", () => {
    const input: Category[] = [
      {
        id: "orphan",
        name: "Osierocona",
        parent_id: "missing",
        type: "expense",
        is_active: true,
      },
      { id: "a", name: "A", parent_id: "b", type: "expense", is_active: true },
      { id: "b", name: "B", parent_id: "a", type: "expense", is_active: true },
    ];
    expect(categoryOptions(input).map(({ id, label }) => [id, label])).toEqual([
      ["b", "A - B"],
      ["a", "B - A"],
      ["orphan", "Osierocona"],
    ]);
    expect(categoryOptions([])).toEqual([]);
  });
});
