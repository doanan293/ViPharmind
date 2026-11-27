import { useHealth } from "~/api/gen/endpoints"

/** The health check rarely changes, so it is reused for five minutes. */
const HEALTH_STALE_TIME_MS = 300_000

/** Which sign-in methods the server offers, read before anyone is signed in. */
export function useSignInOptions(): { phone: boolean; google: boolean } {
  // A degraded check still answers 503 with the same body, so read either.
  const health = useHealth({
    query: {
      meta: { skipAuthRedirect: true },
      staleTime: HEALTH_STALE_TIME_MS,
      retry: false,
    },
  })
  return {
    phone: health.data?.phone_sign_in_enabled === true,
    google: health.data?.google_sign_in_enabled === true,
  }
}
