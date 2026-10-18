import type { CatalogPage } from "./catalogPaging";

/** Merge nearby stores without requesting pages from stores that have finished. */
export function createStoreCatalog<T>(
  stores: string[],
  fetchPage: (store: string, page: number, signal: AbortSignal) => Promise<CatalogPage<T>>,
) {
  let remaining = stores;
  let total = 0;
  return async (page: number, signal: AbortSignal): Promise<CatalogPage<T>> => {
    const active = page === 1 ? stores : remaining;
    const results = await Promise.all(active.map(async store => ({ store, result: await fetchPage(store, page, signal) })));
    // Do not advance any store after a failed or cancelled batch; retry the same page.
    if (signal.aborted) throw new Error("Request cancelled");
    remaining = results.filter(row => row.result.hasNext).map(row => row.store);
    if (page === 1) total = results.reduce((sum, row) => sum + row.result.count, 0);
    return { items: results.flatMap(row => row.result.items), hasNext: remaining.length > 0, count: total };
  };
}
