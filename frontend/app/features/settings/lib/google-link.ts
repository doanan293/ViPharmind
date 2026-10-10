import {
  oauthAssociateGoogleAuthorize,
  oauthAssociateGoogleCallback,
} from "~/api/gen/endpoints"

export async function startGoogleLink(
  assign: (url: string) => void = (url) => window.location.assign(url)
): Promise<void> {
  const { authorization_url: authorizationUrl } =
    await oauthAssociateGoogleAuthorize()
  assign(authorizationUrl)
}

export async function completeGoogleLink(callbackUrl: URL): Promise<void> {
  const { searchParams } = callbackUrl
  await oauthAssociateGoogleCallback({
    code: searchParams.get("code") ?? undefined,
    state: searchParams.get("state") ?? undefined,
  })
}
