import { z } from "zod"

const chatLocationStateSchema = z.object({ initialQuestion: z.string().min(1) })

/** The router location state `NewChat` passes to a new conversation's page. */
export type ChatLocationState = z.infer<typeof chatLocationStateSchema>

/** The first question from the location state, or undefined when the state holds none. */
export function readInitialQuestion(state: unknown): string | undefined {
  const parsed = chatLocationStateSchema.safeParse(state)
  return parsed.success ? parsed.data.initialQuestion : undefined
}
