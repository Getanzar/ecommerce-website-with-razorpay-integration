export type CatalogPage<T> = { items: T[]; hasNext: boolean; count: number };
export function catalogPage<T>(payload: T[] | { results?: T[]; next?: string | null; count?: number }): CatalogPage<T> {
  if (Array.isArray(payload)) return { items: payload, hasNext: false, count: payload.length };
  const items = payload.results || [];
  return { items, hasNext: !!payload.next, count: payload.count ?? items.length };
}

export class CatalogPager<T extends { id: number }> {
  state = { items: [] as T[], hasNext: false, count: 0, loading: true, loadingMore: false, error: "" };
  private listeners = new Set<() => void>();
  private controller?: AbortController;
  private generation = 0;
  private page = 0;
  constructor(private fetchPage: (page: number, signal: AbortSignal) => Promise<CatalogPage<T>>) {}
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.state;
  private update(patch: Partial<typeof this.state>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(fn => fn()); }
  setItems = (update: (rows: T[]) => T[]) => this.update({ items: update(this.state.items) });
  dispose = () => { this.generation++; this.controller?.abort(); };
  refresh = () => { this.dispose(); this.page = 0; return this.load(1); };
  more = () => {
    if (this.state.loading || this.state.loadingMore || !this.state.hasNext) return Promise.resolve();
    return this.load(this.page + 1);
  };
  private async load(page: number) {
    const generation = ++this.generation;
    const controller = new AbortController();
    this.controller = controller;
    this.update({ loading: page === 1, loadingMore: page > 1, error: "", ...(page === 1 ? { items: [], hasNext: false, count: 0 } : {}) });
    try {
      const result = await this.fetchPage(page, controller.signal);
      if (generation !== this.generation) return;
      const rows = page === 1 ? result.items : [...this.state.items, ...result.items];
      this.page = page;
      this.update({ ...result, items: Array.from(new Map(rows.map(row => [row.id, row])).values()) });
    } catch (error) {
      if (generation === this.generation) this.update({ error: error instanceof Error ? error.message : "Could not load products. Please retry." });
    } finally {
      if (generation === this.generation) this.update({ loading: false, loadingMore: false });
    }
  }
}
