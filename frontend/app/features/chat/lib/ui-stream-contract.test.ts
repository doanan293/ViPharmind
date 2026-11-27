import type { UIMessageChunk } from "ai"
import { describe, expect, test } from "vitest"

import {
  CONTRACT_SCENARIOS,
  type ContractScenario,
  dataPartMatchesSchema,
  fixtureText,
  parseFixtureChunks,
  validChunks,
} from "../../../../tests/chat/ui-stream-fixtures"
import {
  messageMetadataSchema,
  pharmaSourceMetadataSchema,
} from "./message-schema"

/** Names the chunk when its data part, pharma source or finish metadata breaks the frontend schema. */
function schemaMismatches(chunk: UIMessageChunk): string[] {
  if (chunk.type.startsWith("data-") && "data" in chunk) {
    const name = chunk.type.slice("data-".length)
    return dataPartMatchesSchema(name, chunk.data) ? [] : [chunk.type]
  }
  if (chunk.type === "source-document") {
    const pharma = chunk.providerMetadata?.pharma
    return pharmaSourceMetadataSchema.safeParse(pharma).success
      ? []
      : [`${chunk.type} ${chunk.sourceId}`]
  }
  if (chunk.type === "finish") {
    return messageMetadataSchema.safeParse(chunk.messageMetadata).success
      ? []
      : [chunk.type]
  }
  return []
}

describe.each(CONTRACT_SCENARIOS)(
  "backend UI stream fixture %s",
  (scenario) => {
    test("parses every chunk with uiMessageChunkSchema and ends with [DONE]", async () => {
      const results = await parseFixtureChunks(scenario)
      expect(results.length).toBeGreaterThan(0)
      const unparsed = results
        .filter((result) => !result.success)
        .map((result) => result.rawValue)
      expect(unparsed).toEqual([])
      const types = validChunks(results).map((chunk) => chunk.type)
      expect(types.slice(0, 2)).toEqual(["start", "data-conversation"])
      expect(types.at(-1)).toBe("finish")
      expect(fixtureText(scenario).trimEnd().endsWith("data: [DONE]")).toBe(
        true
      )
    })

    test("matches the pharma data part, source and metadata schemas", async () => {
      const chunks = validChunks(await parseFixtureChunks(scenario))
      const mismatches = chunks.flatMap(schemaMismatches)
      expect(mismatches).toEqual([])
    })
  }
)

describe("scenario specifics", () => {
  async function chunksOf(scenario: ContractScenario) {
    return validChunks(await parseFixtureChunks(scenario))
  }

  test.each([
    {
      scenario: "completed-with-citations",
      status: "completed",
      finishReason: "stop",
      persisted: true,
      sourceCount: 2,
    },
    {
      scenario: "blocked",
      status: "blocked",
      finishReason: "stop",
      persisted: true,
      sourceCount: 0,
    },
    {
      scenario: "timeout",
      status: "timeout",
      finishReason: "error",
      persisted: true,
      sourceCount: 0,
    },
    {
      scenario: "persist-failed",
      status: "completed",
      finishReason: "stop",
      persisted: false,
      sourceCount: 2,
    },
    {
      scenario: "no-evidence",
      status: "abstained",
      finishReason: "stop",
      persisted: true,
      sourceCount: 0,
    },
  ] as const)(
    "$scenario finishes with status $status, reason $finishReason, persisted $persisted and $sourceCount sources",
    async ({ scenario, status, finishReason, persisted, sourceCount }) => {
      const chunks = await chunksOf(scenario)
      const finish = chunks.find((chunk) => chunk.type === "finish")
      expect(finish?.type === "finish" ? finish.finishReason : undefined).toBe(
        finishReason
      )
      const metadata = messageMetadataSchema.parse(
        finish?.type === "finish" ? finish.messageMetadata : undefined
      )
      expect(metadata.status).toBe(status)
      expect(metadata.persisted).toBe(persisted)
      expect(
        chunks.filter((chunk) => chunk.type === "source-document")
      ).toHaveLength(sourceCount)
    }
  )
})
