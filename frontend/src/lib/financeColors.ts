/** Identity colors are presentation only. Never derive meaning/sign from them. */
export const FINANCE_PALETTE = [
  { name: "Niebieski", hex: "#2563EB" },
  { name: "Turkusowy", hex: "#0D9488" },
  { name: "Fioletowy", hex: "#7C3AED" },
  { name: "Pomarańczowy", hex: "#EA580C" },
  { name: "Różowy", hex: "#DB2777" },
  { name: "Zielony", hex: "#16A34A" },
  { name: "Bursztynowy", hex: "#CA8A04" },
  { name: "Błękitny", hex: "#0284C7" },
  { name: "Czerwony", hex: "#DC2626" },
  { name: "Grafitowy", hex: "#64748B" },
] as const;

function validColor(color: string | null | undefined): string | undefined {
  return color && /^#[\da-f]{6}$/i.test(color)
    ? color.toUpperCase()
    : undefined;
}

export function entityColor(id: string, color?: string | null): string {
  const chosen = validColor(color);
  if (chosen) return chosen;
  let hash = 0;
  for (let index = 0; index < id.length; index++) {
    hash = (Math.imul(hash, 31) + id.charCodeAt(index)) >>> 0;
  }
  return FINANCE_PALETTE[hash % FINANCE_PALETTE.length].hex;
}

type ColoredCategory = {
  id: string;
  parent_id: string | null;
  color?: string | null;
};

export function categoryColorMap(
  categories: readonly ColoredCategory[],
): Map<string, string> {
  const byId = new Map(categories.map((category) => [category.id, category]));
  return new Map(
    categories.map((category) => {
      let current = category;
      const seen = new Set<string>();
      while (!seen.has(current.id)) {
        seen.add(current.id);
        const explicit = validColor(current.color);
        if (explicit) return [category.id, explicit];
        if (!current.parent_id) return [category.id, entityColor(current.id)];
        const parent = byId.get(current.parent_id);
        if (!parent) break;
        current = parent;
      }
      return [category.id, entityColor(category.id)];
    }),
  );
}

/** Pick the higher-contrast foreground; custom colors never hide account initials. */
export function colorInk(hex: string): string {
  const linear = [1, 3, 5].map((index) => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const luminance =
    linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  return luminance > 0.179 ? "#000000" : "#FFFFFF";
}
