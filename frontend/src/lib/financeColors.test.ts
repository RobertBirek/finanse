import { describe, expect, it } from "vitest";
import { categoryColorMap, colorInk, entityColor } from "./financeColors";

describe("persisted finance colors", () => {
  it("keeps account initials readable on white, black and saturated chosen fills", () => {
    expect(colorInk("#FFFFFF")).toBe("#000000");
    expect(colorInk("#000000")).toBe("#FFFFFF");
    expect(colorInk("#2563EB")).toBe("#FFFFFF");
    expect(colorInk("#FFFF00")).toBe("#000000");
  });
  it("uses a chosen hex color and a deterministic automatic color independent of order/name", () => {
    expect(entityColor("account", "#aB12cD")).toBe("#AB12CD");
    expect(entityColor("account", null)).toMatch(/^#[0-9A-F]{6}$/);
    expect(entityColor("account")).toBe(entityColor("account", null));
    expect(entityColor("account", "url(https://invalid)")).toBe(
      entityColor("account"),
    );
  });
  it("inherits nearest parent's explicit or automatic color and respects child overrides", () => {
    const nodes = [
      { id: "root", parent_id: null, color: "#123ABC" },
      { id: "child", parent_id: "root", color: null },
      { id: "grandchild", parent_id: "child", color: null },
      { id: "custom", parent_id: "root", color: "#AABBCC" },
    ];
    const colors = categoryColorMap(nodes);
    expect(colors.get("root")).toBe("#123ABC");
    expect(colors.get("child")).toBe("#123ABC");
    expect(colors.get("grandchild")).toBe("#123ABC");
    expect(colors.get("custom")).toBe("#AABBCC");
    expect(categoryColorMap([...nodes].reverse())).toEqual(colors);
    expect(
      categoryColorMap(nodes.map((n) => ({ ...n, color: null }))).get("child"),
    ).toBe(entityColor("root"));
  });
  it("resolves malformed cycles/orphans safely and changes inherited colors without writing children", () => {
    expect(
      categoryColorMap([
        { id: "a", parent_id: "b" },
        { id: "b", parent_id: "a" },
      ]).get("a"),
    ).toBe(entityColor("a"));
    expect(categoryColorMap([{ id: "a", parent_id: "missing" }]).get("a")).toBe(
      entityColor("a"),
    );
    const child = { id: "child", parent_id: "root", color: null };
    expect(
      categoryColorMap([
        { id: "root", parent_id: null, color: "#FFAA00" },
        child,
      ]).get("child"),
    ).toBe("#FFAA00");
    expect(child.color).toBeNull();
  });
});
