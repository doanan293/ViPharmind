import {
  oauthAssociateGoogleAuthorize,
  oauthAssociateGoogleCallback,
} from "~/api/gen/endpoints"

/** Starts linking Google to the signed-in account by sending the browser to Google; `assign` replaces the navigation in tests. */
export async function startGoogleLink(
  assign: (url: string) => void = (url) => window.location.assign(url)
): Promise<void> {
  const { authorization_url: authorizationUrl } =
    await oauthAssociateGoogleAuthorize()
  assign(authorizationUrl)
}

/** Finishes linking on the callback page; throws the API error when Google or the server refuses. */
export async function completeGoogleLink(callbackUrl: URL): Promise<void> {
  const { searchParams } = callbackUrl
  await oauthAssociateGoogleCallback({
    code: searchParams.get("code") ?? undefined,
    state: searchParams.get("state") ?? undefined,
  })
}
