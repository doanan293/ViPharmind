import type { Route } from "./+types/api-proxy"

/**
 * Same-origin `/api/*` on hosts without a reverse proxy in front (Vercel): forwards the
 * request to the backend and returns its response untouched, cookies and streams included.
 * Locally Vite's proxy, nginx and the E2E proxy answer `/api` before React Router does.
 */

const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000"

// Proves to the backend that a request came through this proxy (one more trusted hop for
// the client IP). A browser's own copy is never forwarded.
const PROXY_HEADER = "x-vipharmind-proxy"

// Hop-by-hop or recomputed by fetch.
const DROPPED_REQUEST_HEADERS = [
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  PROXY_HEADER,
]

// fetch decodes a compressed body, so these would describe bytes the browser never gets.
const DROPPED_RESPONSE_HEADERS = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
]

function backendUrl(request: Request): string {
  const base = (
    process.env.API_INTERNAL_URL ?? DEFAULT_API_INTERNAL_URL
  ).replace(/\/+$/, "")
  const url = new URL(request.url)
  return `${base}${url.pathname}${url.search}`
}

async function forward(request: Request): Promise<Response> {
  const headers = new Headers(request.headers)
  for (const name of DROPPED_REQUEST_HEADERS) {
    headers.delete(name)
  }
  // Ask for an uncompressed body so streamed answers pass through as they arrive.
  headers.set("accept-encoding", "identity")
  const secret = process.env.API_PROXY_SECRET
  if (secret !== undefined && secret !== "") {
    headers.set(PROXY_HEADER, secret)
  }
  const hasBody = request.method !== "GET" && request.method !== "HEAD"
  const upstream = await fetch(backendUrl(request), {
    method: request.method,
    headers,
    body: hasBody ? request.body : null,
    // Streams the request body; required by fetch whenever the body is a stream.
    ...(hasBody ? { duplex: "half" } : {}),
    redirect: "manual",
    signal: request.signal,
  })
  const responseHeaders = new Headers(upstream.headers)
  for (const name of DROPPED_RESPONSE_HEADERS) {
    responseHeaders.delete(name)
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export function loader({ request }: Route.LoaderArgs) {
  return forward(request)
}

export function action({ request }: Route.ActionArgs) {
  return forward(request)
}
