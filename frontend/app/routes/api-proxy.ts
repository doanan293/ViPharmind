import type { Route } from "./+types/api-proxy"

/**
 * Same-origin `/api/*` on hosts without a reverse proxy in front (Vercel): forwards the
 * request to the backend and returns its response untouched, cookies and streams included.
 * Locally Vite's proxy, nginx and the E2E proxy answer `/api` before React Router does.
 */

const DEFAULT_API_INTERNAL_URL = "http://127.0.0.1:8000"

// Hop-by-hop or recomputed by fetch. Without accept-encoding the backend answers
// uncompressed, so the body passes through with its own headers intact.
const DROPPED_REQUEST_HEADERS = [
  "host",
  "connection",
  "content-length",
  "accept-encoding",
  "transfer-encoding",
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
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers,
  })
}

export function loader({ request }: Route.LoaderArgs) {
  return forward(request)
}

export function action({ request }: Route.ActionArgs) {
  return forward(request)
}
