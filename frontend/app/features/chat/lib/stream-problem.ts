import { z } from "zod"

import { ApiError } from "~/api/problem"

const streamProblemSchema = z.object({
  status: z.number().int(),
  code: z.string(),
  title: z.string().optional(),
  detail: z.string().nullish(),
})

/** Reads the problem+json body the AI SDK puts in a failed stream's error message, or null when it holds none. */
export function readStreamProblem(error: Error): ApiError | null {
  let payload: unknown
  try {
    payload = JSON.parse(error.message)
  } catch {
    return null
  }
  const parsed = streamProblemSchema.safeParse(payload)
  if (!parsed.success) {
    return null
  }
  const { status, code, title, detail } = parsed.data
  return new ApiError({
    status,
    code,
    title: title ?? code,
    detail: detail ?? undefined,
  })
}
