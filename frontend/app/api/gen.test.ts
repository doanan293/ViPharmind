import { describe, expect, test } from "vitest"

import {
  getUsersCurrentUserQueryKey,
  getUsersCurrentUserUrl,
} from "~/api/gen/endpoints"
import {
  getPharmaAgentAPIMock,
  getUsersCurrentUserMockHandler,
} from "~/api/gen/endpoints.msw"
import { AuthCookieLoginBody, RegisterRegisterBody } from "~/api/gen/zod"

import { accountView } from "../../tests/utils/account"

describe("generated API client", () => {
  test("query keys are relative API paths, the same on server and client", () => {
    expect(getUsersCurrentUserUrl()).toBe("/api/v1/users/me")
    expect(getUsersCurrentUserQueryKey()).toEqual(["/api/v1/users/me"])
  })

  test("zod schemas validate the auth forms", () => {
    expect(
      AuthCookieLoginBody.safeParse({
        username: "an@example.com",
        password: "correct horse",
      }).success
    ).toBe(true)
    expect(
      RegisterRegisterBody.safeParse({
        email: "not-an-email",
        password: "correct horse",
      }).success
    ).toBe(false)
  })

  test("MSW handlers cover the operations", () => {
    expect(getUsersCurrentUserMockHandler(accountView()).info.path).toBe(
      "*/api/v1/users/me"
    )
    expect(getPharmaAgentAPIMock().length).toBeGreaterThan(0)
  })
})
