import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

import type { ApiError } from "~/api/problem"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

const HTTP_UNAUTHORIZED = 401
const HTTP_SERVICE_UNAVAILABLE = 503

/** What `useStreamProblemHandler` changes in the chat session when a stream fails. */
export type StreamProblemActions = {
  /** Puts the question that failed back into the composer. */
  restoreDraft: () => void
  setComposerError: (message: string) => void
  setAgentUnavailable: (unavailable: boolean) => void
}

/**
 * Returns the reaction to a problem+json stream error: sign in again on 401, leave a
 * conversation that no longer exists, show the agent banner on 503, and otherwise show the
 * error under the composer. The failed question always goes back into the composer.
 */
export function useStreamProblemHandler({
  restoreDraft,
  setComposerError,
  setAgentUnavailable,
}: StreamProblemActions): (problem: ApiError) => void {
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const location = useLocation()
  const returnTo = location.pathname + location.search

  return useCallback(
    (problem: ApiError) => {
      restoreDraft()
      if (problem.status === HTTP_UNAUTHORIZED) {
        void navigate(`/login?next=${encodeURIComponent(returnTo)}`)
      } else if (problem.code === "CONVERSATION_NOT_FOUND") {
        toast.add({ title: apiErrorMessage(problem, tErrors), type: "error" })
        void navigate("/chat", { replace: true })
      } else if (problem.status === HTTP_SERVICE_UNAVAILABLE) {
        setAgentUnavailable(true)
      } else {
        setComposerError(problem.detail ?? apiErrorMessage(problem, tErrors))
      }
    },
    [
      restoreDraft,
      setComposerError,
      setAgentUnavailable,
      navigate,
      returnTo,
      tErrors,
    ]
  )
}
