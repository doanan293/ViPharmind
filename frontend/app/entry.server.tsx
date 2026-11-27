import { PassThrough } from "node:stream"

import { createReadableStreamFromReadable } from "@react-router/node"
import { isbot } from "isbot"
import type { RenderToPipeableStreamOptions } from "react-dom/server"
import { renderToPipeableStream } from "react-dom/server"
import { I18nextProvider } from "react-i18next"
import type { EntryContext, RouterContextProvider } from "react-router"
import { ServerRouter } from "react-router"

import { getInstance } from "~/i18n/middleware.server"

/**
 * How long, in ms, React may keep streaming a response; React Router reads this export and
 * the render aborts shortly after it.
 */
export const streamTimeout = 5_000

/**
 * Extra time after `streamTimeout` before the render is aborted, so React can flush its
 * fallbacks first.
 */
const ABORT_DELAY_MS = 1_000

/** Status of a response whose rendering hit an error after the shell was sent. */
const INTERNAL_SERVER_ERROR = 500

/**
 * Server-renders a document request with the request's i18n instance. Bots get the fully
 * rendered page, browsers a stream from the shell on; HEAD gets headers only.
 */
export default function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
  loadContext: RouterContextProvider
) {
  // https://httpwg.org/specs/rfc9110.html#HEAD
  if (request.method.toUpperCase() === "HEAD") {
    return new Response(null, {
      status: responseStatusCode,
      headers: responseHeaders,
    })
  }

  return new Promise<Response>((resolve, reject) => {
    let shellRendered = false
    let statusCode = responseStatusCode
    const userAgent = request.headers.get("user-agent")

    // Bots wait for all content so crawlers get the full page.
    const readyOption: keyof RenderToPipeableStreamOptions =
      userAgent !== null && isbot(userAgent) ? "onAllReady" : "onShellReady"

    let timeoutId: ReturnType<typeof setTimeout> | undefined = setTimeout(
      () => {
        abort()
      },
      streamTimeout + ABORT_DELAY_MS
    )

    const { pipe, abort } = renderToPipeableStream(
      <I18nextProvider i18n={getInstance(loadContext)}>
        <ServerRouter context={routerContext} url={request.url} />
      </I18nextProvider>,
      {
        [readyOption]() {
          shellRendered = true
          const body = new PassThrough({
            final(callback) {
              clearTimeout(timeoutId)
              timeoutId = undefined
              callback()
            },
          })
          const stream = createReadableStreamFromReadable(body)

          responseHeaders.set("Content-Type", "text/html")

          pipe(body)

          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: statusCode,
            })
          )
        },
        onShellError(error: unknown) {
          reject(error instanceof Error ? error : new Error(String(error)))
        },
        onError(error: unknown) {
          statusCode = INTERNAL_SERVER_ERROR
          // Errors before the shell reject above and are logged by React Router.
          if (shellRendered) {
            console.error(error)
          }
        },
      }
    )
  })
}
