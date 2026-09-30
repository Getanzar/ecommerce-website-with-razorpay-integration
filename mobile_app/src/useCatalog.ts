import { useEffect, useMemo, useSyncExternalStore } from "react";
import { CatalogPage, CatalogPager } from "./catalogPaging";

export function useCatalog<T extends { id: number }>(key: string, fetchPage: (page: number, signal: AbortSignal) => Promise<CatalogPage<T>>, enabled = true) {
  // The key contains every filter and auth context captured by fetchPage.
  const pager = useMemo(() => new CatalogPager(fetchPage), [key]);
  const state = useSyncExternalStore(pager.subscribe, pager.snapshot);
  useEffect(() => {
    const timer = enabled ? setTimeout(() => void pager.refresh(), 250) : undefined;
    return () => { if (timer !== undefined) clearTimeout(timer); pager.dispose(); };
  }, [pager, enabled]);
  return { ...state, refresh: pager.refresh, more: pager.more, setItems: pager.setItems };
}
