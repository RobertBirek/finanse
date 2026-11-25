export function parseStatementBalance(input: string): string | null {
  const parts = /^(-?)(\d{1,17})(?:[,.](\d{1,2}))?$/.exec(input.trim());
  if (!parts) return null;
  const minor = BigInt(
    `${parts[1]}${parts[2]}${(parts[3] ?? "").padEnd(2, "0")}`,
  );
  return minor >= -(2n ** 63n) && minor < 2n ** 63n ? String(minor) : null;
}
