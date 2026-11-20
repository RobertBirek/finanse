export function listPage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 && page <= 200000 ? page : 1;
}

export function setListPage(
  params: URLSearchParams,
  key: string,
  page: number,
) {
  if (page <= 1) params.delete(key);
  else params.set(key, String(page));
}
