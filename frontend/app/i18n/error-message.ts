import type { TFunction } from "i18next"

import { isApiError } from "~/api/problem"
import { resources } from "~/i18n/config"

/** A problem `code` that has a translated message in the `errors` namespace. */
export type ErrorCode = keyof (typeof resources)["vi"]["errors"]

/** True when `code` has a translation in `errors`, so `t(code)` is safe. */
export function isErrorCode(code: string): code is ErrorCode {
  return Object.hasOwn(resources.vi.errors, code)
}

/** Message for a failed request: translated by problem code, else the problem title. */
export function apiErrorMessage(
  error: unknown,
  t: TFunction<"errors">
): string {
  if (isApiError(error)) {
    if (isErrorCode(error.code)) {
      return t(error.code)
    }
    if (error.message !== "") {
      return error.message
    }
  }
  return t("UNKNOWN")
}
