/** `?page=N` for list routes; anything invalid means the first page. */
export function parsePage(search: Record<string, unknown>): { page?: number } {
  const page = Math.floor(Number(search.page))
  return Number.isFinite(page) && page > 1 ? { page } : {}
}
