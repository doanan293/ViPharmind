import type { InfiniteData } from "@tanstack/react-query"

/**
 * The pages an infinite query has loaded, or undefined before the first one arrives.
 * Typed explicitly so callers can branch on "not loaded yet" without re-reading `query.data`.
 */
export function loadedPages<TPage>(
  data: InfiniteData<TPage, unknown> | undefined
): TPage[] | undefined {
  return data?.pages
}
