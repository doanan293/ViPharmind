import { createChat } from "@shadcn/helpers/ai-sdk"
import { createUIMessageStreamResponse } from "ai"
import { type HttpHandler, HttpResponse, http } from "msw"
import { z } from "zod"

import { getChatStreamUrl } from "~/api/gen/endpoints"
import type { MessageMetadata } from "~/api/gen/schemas"
import type { PharmaUIMessage } from "~/features/chat/lib/message-schema"

import { CREATED_AT, pharmaSource } from "./fixtures"

const streamRequestSchema = z.object({
  conversation_id: z.string(),
  message: z.string(),
})

export type StreamRequest = z.infer<typeof streamRequestSchema>
export type ScriptedChat = ReturnType<typeof createChat<PharmaUIMessage>>

const STREAM_URL = `*${getChatStreamUrl()}`

function finishMetadata(
  overrides: Partial<MessageMetadata> = {}
): MessageMetadata {
  return {
    status: "completed",
    createdAt: CREATED_AT,
    errorCode: null,
    usage: {
      llmCalls: 4,
      promptTokens: 900,
      completionTokens: 120,
      searchRounds: 1,
    },
    runId: "00000000000000000000000000000003",
    persisted: true,
    ...overrides,
  }
}

export type AnswerOptions = {
  id?: string
  conversationId?: string
  title?: string
  text?: string
  metadata?: Partial<MessageMetadata>
  slow?: boolean
  withSource?: boolean
}

/** The callback form of `assistant(...)`, which scripts a turn through a writer. */
type AssistantScript = Extract<
  Parameters<ScriptedChat["assistant"]>[0],
  (context: never) => void
>
type ChatWriter = Parameters<AssistantScript>[0]["writer"]

/** How long a slow answer stays in the "searching" phase. */
const SLOW_SEARCH_MS = 600
/** Delay between streamed text chunks of a slow answer. */
const SLOW_TEXT_DELAY_MS = 150
const DEFAULT_ANSWER =
  "Người lớn uống 0,5–1 g mỗi 4–6 giờ, tối đa 4 g mỗi ngày [1]."

function writeSearchPhase(writer: ChatWriter, options: AnswerOptions): void {
  writer.data({
    type: "data-conversation",
    data: {
      id: options.conversationId ?? "c1",
      title: options.title ?? "Cuộc trò chuyện mới",
    },
    transient: true,
  })
  writer.data({
    type: "data-phase",
    id: "phase",
    data: { phase: "searching", round: 1 },
  })
  if (options.slow === true) {
    writer.sleep(SLOW_SEARCH_MS)
  }
}

function writeEvidence(writer: ChatWriter): void {
  writer.data({
    type: "data-phase",
    id: "phase",
    data: { phase: "answering" },
  })
  writer.data({
    type: "data-evidence",
    id: "evidence",
    data: {
      items: [
        {
          index: 1,
          source: "Dược thư Quốc gia Việt Nam (Xuất bản lần thứ 2)",
          title: "Paracetamol",
          section: "Liều lượng và cách dùng",
          startPage: 812,
          endPage: 813,
          snippet: "Người lớn và trẻ em trên 12 tuổi…",
        },
      ],
    },
  })
}

function writeText(writer: ChatWriter, text: string, slow: boolean): void {
  if (text === "") {
    return
  }
  if (slow) {
    writer.text(text, { delayMs: SLOW_TEXT_DELAY_MS })
  } else {
    writer.text(text)
  }
}

function writeSource(writer: ChatWriter): void {
  writer.sourceDocument({
    sourceId: "chunk-1",
    mediaType: "text/markdown",
    title: "Paracetamol › Liều lượng và cách dùng",
    providerMetadata: { pharma: { ...pharmaSource(1) } },
  })
}

export function answerChat(
  question: string,
  options: AnswerOptions = {}
): ScriptedChat {
  const text = options.text ?? DEFAULT_ANSWER
  return createChat<PharmaUIMessage>()
    .user(question)
    .assistant(
      ({ writer }) => {
        writeSearchPhase(writer, options)
        writeEvidence(writer)
        writeText(writer, text, options.slow === true)
        if (options.withSource !== false) {
          writeSource(writer)
        }
      },
      { id: options.id ?? "a-new", metadata: finishMetadata(options.metadata) }
    )
}

export function chatStreamHandler(
  chats: readonly ScriptedChat[],
  requests: StreamRequest[] = [],
  delayMs = 0
): HttpHandler {
  let served = 0
  return http.post(STREAM_URL, async ({ request }) => {
    const body = streamRequestSchema.parse(await request.json())
    requests.push(body)
    const chat = chats[Math.min(served, chats.length - 1)]
    served += 1
    if (chat === undefined) {
      return HttpResponse.error()
    }
    const stream = await chat.transport({ delayMs }).sendMessages({
      trigger: "submit-message",
      chatId: body.conversation_id,
      messageId: undefined,
      messages: chat.get(1),
      abortSignal: request.signal,
    })
    return createUIMessageStreamResponse({ stream })
  })
}

export function problemHandler(
  status: number,
  code: string,
  detail?: string
): HttpHandler {
  return http.post(STREAM_URL, () =>
    HttpResponse.json(
      {
        type: `urn:pharma-agent:problem:${code.toLowerCase().replaceAll("_", "-")}`,
        title: code,
        status,
        code,
        ...(detail === undefined ? {} : { detail }),
      },
      { status, headers: { "Content-Type": "application/problem+json" } }
    )
  )
}

export function networkErrorHandler(): HttpHandler {
  return http.post(STREAM_URL, () => HttpResponse.error())
}
