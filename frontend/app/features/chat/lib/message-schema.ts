import type { ChatInit, UIMessage } from "ai"
import { z } from "zod"

import type { MessageMetadata, PharmaDataParts } from "~/api/gen/schemas"
import { ListMessagesResponse } from "~/api/gen/zod"

/** The agent's steps in the order the stream reports them in `data-phase` parts. */
export const AGENT_PHASES = [
  "guarding",
  "understanding",
  "searching",
  "reading",
  "answering",
] as const

/** One step of the agent, as reported in a `data-phase` part. */
export type AgentPhase = (typeof AGENT_PHASES)[number]

const evidenceItemSchema = z.object({
  index: z.number().int(),
  source: z.string(),
  title: z.string(),
  section: z.string(),
  startPage: z.number().int().nullable(),
  endPage: z.number().int().nullable(),
  snippet: z.string(),
})

/** Validates the `pharma` provider metadata of a source part: a cited passage and whether it is current. */
export const pharmaSourceMetadataSchema = evidenceItemSchema.extend({
  isCurrent: z.boolean(),
})

/** The custom data parts of the chat stream, by name without the `data-` prefix. */
export type PharmaDataPartTypes = {
  [Name in keyof PharmaDataParts]: PharmaDataParts[Name]
}

/** A chat message as the AI SDK holds it, with Pharma metadata and data parts. */
export type PharmaUIMessage = UIMessage<MessageMetadata, PharmaDataPartTypes>

/** One part of a `PharmaUIMessage`. */
export type PharmaMessagePart = PharmaUIMessage["parts"][number]

/** The schemas `useChat` validates the stream's custom data parts with. */
export const pharmaDataPartSchemas = {
  phase: z.object({
    phase: z.enum(AGENT_PHASES),
    round: z.number().int().nullable().optional(),
  }),
  evidence: z.object({ items: z.array(evidenceItemSchema) }),
  conversation: z.object({ id: z.string(), title: z.string() }),
} satisfies NonNullable<ChatInit<PharmaUIMessage>["dataPartSchemas"]>

/** The schema `useChat` validates message metadata with, taken from the generated history response schema. */
export const messageMetadataSchema = ListMessagesResponse.shape.items.element
  .shape.metadata satisfies NonNullable<
  ChatInit<PharmaUIMessage>["messageMetadataSchema"]
>
