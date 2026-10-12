import { useHealth } from "~/api/gen/endpoints"

/** Which sign-in methods the server offers, read before anyone is signed in. */
export function useSignInOptions(): { phone: boolean; google: boolean } {
  // A degraded check still answers 503 with the same body, so read either.
  const health = useHealth({
    query: {
      meta: { skipAuthRedirect: true },
      staleTime: 5 * 60_000,
      retry: false,
    },
  })
  return {
    phone: health.data?.phone_sign_in_enabled === true,
    google: health.data?.google_sign_in_enabled === true,
  }
}
