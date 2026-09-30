/** Retry reads only. A timed-out write may already have succeeded on the server. */
export async function fetchWithRetry(url: string, options: RequestInit, fetcher: typeof fetch = fetch, timeoutMs = 30000): Promise<Response> {
  const read = !options.method || options.method.toUpperCase() === "GET";
  for (let attempt = 0; ; attempt++) {
    try {
      const result = await fetcher(url, { ...options, signal: options.signal ?? AbortSignal.timeout(timeoutMs) });
      if (read && attempt < 2 && [502, 503, 504].includes(result.status)) {
        await new Promise(resolve => setTimeout(resolve, 300 * (attempt + 1))); continue;
      }
      return result;
    } catch (error) {
      if (!read || attempt >= 2 || options.signal?.aborted) throw error;
      await new Promise(resolve => setTimeout(resolve, 300 * (attempt + 1)));
    }
  }
}
