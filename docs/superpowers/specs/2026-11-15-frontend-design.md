# Thiết kế frontend ViPharmind

Ngày: 2026-11-15. Trạng thái: mô tả mã hiện hành trên nhánh `v2.0.0` (commit `9732e8e`). Thay cho
spec `frontend/docs/superpowers/specs/2026-09-13-frontend-v1-design.md` và phần frontend trong hai
spec ngày 2026-10-10 (luồng tài khoản, ra mắt sản phẩm).

## 1. Mục tiêu và phạm vi

Web client cho trợ lý tra cứu thuốc ViPharmind. Người dùng đăng nhập, hỏi đáp có trích dẫn nguồn,
quản lý tài khoản, tổ chức và bộ tài liệu (collection) của mình; superadmin có trang quản trị. Trang
public (giới thiệu, chính sách, điều khoản) render phía server để có SEO.

Phạm vi của spec này là mã trong `frontend/`: stack, cách render, tầng dữ liệu, các màn hình, quy tắc
giao diện, test và cách chạy. Quy tắc nghiệp vụ phía server (quyền, hạn mức, luồng OTP, pipeline xuất
bản) thuộc spec khác, xem mục 10.

Mục tiêu thiết kế:

1. Dùng thư viện có sẵn thay vì tự dựng: shadcn cho mọi widget, AI SDK cho chat, orval sinh client.
2. Kiểu dữ liệu đi thẳng từ OpenAPI của backend; dữ liệu mạng luôn có type do orval sinh hoặc được
   parse bằng zod.
3. Trình duyệt chỉ nói chuyện với một origin, nên cookie session là first-party và chat stream đi
   qua cùng proxy.
4. Tiếng Việt mặc định, tiếng Anh thứ hai; không có chuỗi giao diện viết cứng trong component.

## 2. Stack

Phiên bản pin chính xác trong `frontend/package.json` (cài bằng `--save-exact`).

| Tầng | Lựa chọn |
| --- | --- |
| Framework | React Router 8.3 framework mode, `ssr: true`; React 19.3; Vite 8; Node ≥ 24.15, npm |
| UI | shadcn CLI 4.21, style `base-nova` (Base UI 1.8), Tailwind 4, `@tailwindcss/typography`, lucide; toast của shadcn |
| Chat | `ai` 7 và `@ai-sdk/react` (`useChat`, `DefaultChatTransport`); `message-scroller` của shadcn (`@shadcn/react` 0.3); Streamdown 2.6 với `@streamdown/code`, `@streamdown/math` |
| Soạn tài liệu | Tiptap 3 (`starter-kit`, bảng, Markdown) |
| Bảng dữ liệu | `@tanstack/react-table` qua `data-table` của block `dashboard-01` |
| Dữ liệu | TanStack Query 5; client, zod schema và handler MSW sinh bằng orval 8 từ `frontend/openapi.json` |
| Form | react-hook-form 7 + `@hookform/resolvers` + zod 4; `libphonenumber-js` cho số điện thoại; `input-otp` cho mã |
| i18n | i18next 26, react-i18next 17, remix-i18next 8 |
| Theme | remix-themes 2.0 (cookie session ký bằng `THEME_COOKIE_SECRET`) |
| Ngôn ngữ, lint | TypeScript 7 strict + `noUncheckedIndexedAccess`; Oxlint type-aware (`oxlint-tsgolint`) `--deny-warnings`; Prettier + `prettier-plugin-tailwindcss` |
| Test | Vitest 5 (project `unit` trên Node, project `browser` trên Chromium qua `@vitest/browser-playwright`), MSW 2, `@shadcn/helpers`, Playwright 1.63 |

## 3. Kiến trúc lúc chạy

```text
Production (Vercel):
Browser ──► vipharmind.vercel.app (React Router server, Vercel Function)
              ├─ /api/*  ──► route api-proxy.ts ──► API_INTERNAL_URL (Vercel project vipharmind-api)
              └─ /*      ──► SSR, prerender, hoặc khung trang client-only

Local stack (compose.yaml):
Browser ──► nginx :WEB_PORT ── /api/ ──► backend:8000   (proxy_buffering off, gzip off, read_timeout 1h)
                             └ /     ──► frontend:3000  (react-router-serve)

Dev: `react-router dev` cổng 3000, Vite proxy /api → API_INTERNAL_URL (mặc định http://127.0.0.1:8000)
E2E: tests/e2e/proxy.ts (http-proxy-3) đóng vai nginx trên cổng 3200
```

- `app/routes/api-proxy.ts` chuyển tiếp method, header (bỏ `host` và header hop-by-hop), body và
  response, kể cả stream. Nó xin body không nén (`accept-encoding: identity`) để câu trả lời chảy
  ra ngay, và gắn header `X-Vipharmind-Proxy` bằng `API_PROXY_SECRET` để backend tin IP client mà
  proxy chuyển tiếp. Backend không với tới được thì trả 503 problem+json mã `BACKEND_UNAVAILABLE`.
- Ở local, Vite proxy, nginx và proxy E2E trả lời `/api` trước, nên route này không chạy; cùng một
  build chạy được cả hai nơi mà không có mã riêng cho test.
- Biến môi trường (`frontend/.env.example`): `API_INTERNAL_URL`, `PUBLIC_SITE_URL` (đọc lúc build cho
  canonical và hreflang của trang prerender), `API_PROXY_SECRET`, `THEME_COOKIE_SECRET`.
- `vercel.json` có cron hằng ngày gọi `/api/v1/health` để cluster Qdrant miễn phí không bị tạm dừng.
  Chi tiết deploy cả hai project Vercel: spec mảng 4 (mục 10).

## 4. Bố cục mã

```text
frontend/
  app/
    root.tsx            Layout (ThemeProvider, <html lang>), middleware i18n, QueryClientProvider,
                        Toaster, TooltipProvider, ErrorBoundary
    routes.ts           khai báo route (mục 5)
    routes/             module route mỏng, chỉ ghép feature
    features/<f>/       components/, hooks/, lib/; test đặt cạnh code
                        admin, audit, auth, chat, collections, conversations, landing, legal,
                        organizations, settings, shell
    components/ui/      shadcn sinh bằng CLI
    components/         composition dùng chung: tags-input, name-form, code-step, otp-code-field,
                        section-cards, data-table, document
    api/                fetcher.ts (mutator orval), query-client.ts, problem.ts, gen/ (output orval, commit)
    i18n/               config, middleware.server, locale.server, error-message, zod-locale,
                        resources/{vi,en}/<namespace>.json
    lib/  hooks/        csrf, form-errors, phone, theme.server, utils; use-mobile, use-countdown
  tests/                chỉ mã hỗ trợ: setup Vitest, MSW, fixture chat, helper render; tests/e2e/*.e2e.ts
  openapi.json  orval.config.ts  playwright.config.ts  vitest.config.ts  Dockerfile  vercel.json
```

Ranh giới import (ép bằng `.oxlintrc.json` và `app/architecture.test.ts`): code dùng chung không
import feature hay route; feature không import route; giữa các feature chỉ có các hướng
`chat → conversations`, `shell → auth, conversations`, `organizations → audit`,
`admin → auth, chat, audit`; không có vòng import. Quy tắc chung về bố cục và vị trí file test của
cả ba project nằm ở spec mảng 5; bảng hướng import chi tiết nằm trong `frontend/README.md`.

## 5. Route và cách render

| URL | Module | Render |
| --- | --- | --- |
| `/`, `/en` | `public/landing.tsx` (route id `landing-vi`, `landing-en`) | SSR + prerender; meta title, description, OG, `hreflang` vi, en, x-default |
| `/privacy`, `/en/privacy`, `/terms`, `/en/terms` | `public/privacy.tsx`, `public/terms.tsx` | SSR + prerender, hai ngôn ngữ |
| `/invitations/:token` | `public/invitation.tsx` | Public; xem trước lời mời, nút Đăng nhập, Đăng ký kèm `next=` |
| `/login`, `/register`, `/forgot-password` | `auth/*` | Khung SSR, form chạy ở client; đã đăng nhập thì chuyển thẳng |
| `/auth/google/callback`, `/auth/google/link-callback` | `auth/google-*.tsx` | Chỉ client |
| `/chat/:conversationId?` | `app/chat.tsx` | Chỉ client (`clientLoader` + `HydrateFallback`) |
| `/settings`, `/activity` | `app/settings.tsx`, `app/activity.tsx` | Chỉ client |
| `/organizations`, `/organizations/:organizationId/:tab?` | `app/organization(s).tsx` | Chỉ client |
| `/collections`, `/collections/:collectionId/:tab?`, `/collections/:collectionId/documents/:documentId` | `app/collection(s).tsx`, `app/document.tsx` (`documentId` là `new` thì tạo tài liệu mới) | Chỉ client |
| `/admin/:section?` | `app/admin.tsx` | Chỉ client; người không phải superadmin nhận 404 |
| `/api/*` | `api-proxy.ts` | Proxy (mục 3) |
| `POST /actions/locale`, `POST /actions/theme` | `actions/*` | Ghi cookie `lng`, cookie theme |
| `*` | `not-found.tsx` | SSR, có i18n |

Mọi route riêng tư nằm trong `routes/app/layout.tsx`. Layout này chạy `requireUser` ở
`clientMiddleware` (mỗi lần chuyển trang ở client) và ở `clientLoader` với `hydrate = true` (lần tải
trang đầu). `requireUser` gọi `queryClient.ensureQueryData(currentUserQueryOptions())`; lỗi 401 thì
`redirect("/login?next=<path>")`. Không dựa vào middleware phía server vì nó không chạy khi chuyển
trang ở client.

## 6. Tầng dữ liệu

### 6.1 orval

- Output `api`: `client: "react-query"`, `httpClient: "fetch"`, `mode: "split"`, mutator
  `app/api/fetcher.ts`, TanStack Query v5, `useInfinite` theo tham số `cursor`, sinh handler MSW.
- Output `zod`: một file `app/api/gen/zod.ts`, zod 4, dùng cho form và kiểm dữ liệu stream.
- `npm run api:openapi` gọi `pharma-agent export-openapi` của backend để ghi `openapi.json`;
  `npm run api:generate` chạy orval; `npm run api:check` (cũng là hook pre-commit) báo lỗi khi output
  trong `app/api/gen/` không khớp `openapi.json`.

### 6.2 Fetcher và lỗi

- Mọi request chạy trên trình duyệt (clientLoader và TanStack Query), URL tương đối `/api/v1/...`,
  `credentials: "same-origin"`, gửi `Accept-Language` theo `<html lang>`.
- POST, PUT, PATCH, DELETE gắn header `x-csrftoken` đọc từ cookie `csrftoken`.
- Response lỗi `application/problem+json` thành `ApiError {status, code, title, detail, errors[]}`.
  Thông báo hiển thị lấy từ namespace `errors` theo `code` (`apiErrorMessage`), thiếu thì dùng
  `title`.
- `QueryCache.onError` và `MutationCache.onError` đưa lỗi 401 về `/login?next=`, trừ query đánh dấu
  `meta.skipAuthRedirect` (ví dụ health đọc trước khi đăng nhập). `retry` bỏ qua lỗi 4xx.

### 6.3 Form

react-hook-form + `zodResolver` với schema orval sinh (có thể mở rộng), giao diện bằng `Field`,
`FieldLabel`, `FieldError` của shadcn. Lỗi 422 trong `errors[]` gắn vào đúng field bằng
`form.setError`; lỗi khác vào lỗi cấp form. Thông báo lỗi của zod cũng dịch theo ngôn ngữ
(`i18n/zod-locale.ts`).

## 7. Màn hình

### 7.1 Chat

```text
routes/app/chat.tsx
└─ ChatThread(conversationId?)
   ├─ không có id: NewChat (Empty + Composer + SourcesPopover)
   └─ có id: useListMessagesInfinite (trang đầu) → ChatSession
        ├─ useChat<PharmaUIMessage>({ id, messages, transport, dataPartSchemas, messageMetadataSchema })
        ├─ MessageScroller (giữ vị trí khi chèn tin cũ) → Message/Bubble → MessageParts
        ├─ OlderMessagesLoader
        └─ Composer (InputGroup + Textarea, nút Gửi/Dừng, giới hạn độ dài từ zod của orval)
ConversationSidebar nằm trong AppSidebar (feature conversations)
```

- `PharmaUIMessage = UIMessage<MessageMetadata, PharmaDataParts>`; type và schema lấy từ output
  orval nên stream được kiểm bằng đúng type của backend. Định dạng UI Message Stream do spec mảng 1
  quy định.
- **Transport** (`lib/chat-transport.ts`): `DefaultChatTransport` tới `getChatStreamUrl()`,
  `credentials: "same-origin"`, header CSRF; body là `{conversation_id, message}` với `message` là
  tin người dùng cuối cùng.
- **Hội thoại mới**: `POST /conversations`; nếu người dùng đã thu hẹp nguồn thì
  `PATCH /conversations/{id} {collection_ids}` trước (lỗi thì dừng, giữ bản nháp); rồi
  `navigate("/chat/<id>", {replace: true, state: {initialQuestion}})` và gửi câu hỏi. Part
  `data-conversation` cập nhật tiêu đề trong cache sidebar.
- **Phạm vi nguồn** (`SourcesPopover`): `combobox` chọn nhiều có ô tìm, nhóm Công khai, từng tổ
  chức, Của tôi, Khác, và nút "Tất cả nguồn tôi được thấy". `null` là tìm mọi collection được thấy.
  Danh sách collection chỉ tải khi mở popup; lựa chọn hiện ngay rồi mới lưu vào hội thoại.
- **Tải tin cũ**: chỉ tải khi người dùng đã cuộn lên đầu, hoặc khi đã đo được thread vừa khung nhìn
  (ResizeObserver); `MessageScroller` giữ vị trí đọc khi chèn ở đầu. `MessageScrollerItem` không dùng
  `content-visibility: auto` vì làm lệch vị trí khi chèn.
- **Hiển thị** (`describeMessage` → `MessageParts`):

| Dữ liệu | Hiển thị |
| --- | --- |
| `data-phase` | `agent-status`, nhãn i18n theo phase (`guarding`, `understanding`, `searching`, `reading`, `answering`); chỉ hiện khi đang stream |
| `data-evidence` | `retrieval-chunks` (`collapsible` + `item`) |
| `text` | `AnswerMarkdown`: Streamdown, `[n]` đổi thành thẻ `cite-ref` trước khi render, thẻ đó render bằng `CitationMarker` |
| `source-document` | `SourcesList` / `sources`: nút "N nguồn" mở danh sách |
| `metadata.status` `blocked`, `redirected` | `guardrail-notice` (`alert`) |
| `metadata.status` `error`, `timeout`, hoặc lỗi mạng | `error-state` với nút thử lại đúng câu hỏi |
| `metadata.persisted === false` | Không cho phản hồi; toast báo không lưu được lượt này |

- **Trích dẫn**: `CitationMarker` dùng `inline-citation` trên `hover-card` để xem trước nguồn, mục,
  trang. Bấm marker hoặc thẻ nguồn mở `CitationSheet` (`Sheet` trên desktop, `Drawer` trên mobile)
  gọi `GET /messages/{id}/citations/{index}` và hiện tài liệu, mục, trang, cảnh báo khi nguồn đã có
  phiên bản mới (`is_current`), và toàn văn đoạn được trích bằng Streamdown tĩnh. Mỗi trích dẫn là
  đúng một chunk.
- **Phản hồi**: Copy, 👍, 👎 (`POST /messages/{id}/feedback`); 👎 mở `feedback-dialog`
  (`toggle-group` lý do + `textarea` ghi chú). Trạng thái đầu lấy từ `metadata.feedback`, cập nhật
  lạc quan vào cache.
- **Lỗi**: 401 về đăng nhập; 404 `CONVERSATION_NOT_FOUND` toast rồi về `/chat`; 503 (kể cả
  `BACKEND_UNAVAILABLE`) hiện `AgentUnavailableBanner`; Dừng gọi `stop()`, lượt không được lưu.
- Không có tạo lại, sửa, rẽ nhánh câu trả lời.

### 7.2 Tài khoản

| Màn hình | Nội dung |
| --- | --- |
| `/register` | Tab email (tên, email, mật khẩu, rồi nhập mã) và tab số điện thoại (số, rồi nhập mã) |
| `/login` | Email và mật khẩu, số điện thoại kèm mã, nút Google. `EMAIL_NOT_VERIFIED` thì tự gửi mã và chuyển sang bước nhập mã |
| `/forgot-password` | Email, rồi mã và mật khẩu mới |
| `/settings` | Hồ sơ (tên hiển thị); Tài khoản (email, số điện thoại, mật khẩu, liên kết Google, danh sách phiên); ngôn ngữ; giao diện sáng, tối, theo hệ thống |
| `/activity` | Nhật ký thao tác của chính mình |

Tab số điện thoại và nút Google chỉ hiện khi health báo `phone_sign_in_enabled`,
`google_sign_in_enabled` (`useSignInOptions`); tài khoản đã liên kết Google vẫn thấy mục đó để gỡ.
Thành phần dùng chung: `code-step` và `otp-code-field` (dán cả mã, nút gửi lại có đếm ngược), ô số
điện thoại mặc định `+84`. Quy tắc OTP, giới hạn gửi và quy tắc liên kết Google: spec mảng 4.

### 7.3 Tổ chức, collection, quản trị

| Feature | Nội dung |
| --- | --- |
| `organizations` | Danh sách, tạo tổ chức; trang chi tiết có tab Thành viên, Lời mời, Collection, Nhật ký; tab không có quyền thì ẩn; xoá thành viên phải xác nhận. Trang nhận lời mời `/invitations/:token` |
| `collections` | Danh sách collection (`item`) kèm thanh hạn mức (`progress`). Trang collection có tab Tài liệu, Thuật ngữ, Tên gọi dân gian, Bản phát hành, nút Xuất bản và hộp tiến độ job (poll). Trang soạn tài liệu dùng Tiptap với thanh công cụ `toggle`, tải lên `.txt`/`.md` mở trong cùng trình soạn thảo. "Công khai" chỉ hiện với superadmin; collection hệ thống chỉ đọc |
| `audit` | Danh sách sự kiện dùng chung, mỗi sự kiện là một câu dựng từ `action`, `details` và `subject_name` (tên người được nhắc tới, "một thành viên" khi không biết); thao tác của superadmin có nhãn riêng |
| `admin` | Theo block `dashboard-01`: thẻ số liệu (`section-cards`) và các mục Người dùng, Tổ chức, Collection, Job (cột collection hiện tên lấy từ danh sách collection), Nhật ký, bảng là `data-table`. Xem hội thoại của người dùng bằng `ReadOnlyThread`, dùng lại component tin nhắn của `chat` |
| `legal`, `landing` | Trang giới thiệu, Chính sách quyền riêng tư, Điều khoản sử dụng, hai ngôn ngữ, prerender; footer có link |

Quyền, hạn mức và luồng xuất bản do backend quyết định; frontend chỉ ẩn những gì người dùng không có
quyền. Chi tiết: spec mảng 4.

### 7.4 Khung ứng dụng

Block `dashboard-01` của shadcn: `AppSidebar` (logo, `NavMain` gồm Chat, Tổ chức, Collection, Hoạt
động; danh sách hội thoại; `NavSecondary` gồm Cài đặt và Quản trị khi là superadmin), `NavUser` (menu
người dùng, đăng xuất), `SiteHeader`. Sidebar thu gọn thành icon; trên mobile là sheet.

## 8. i18n, theme, giao diện

- **i18n**: remix-i18next middleware ở `root.tsx`. Thứ tự xác định ngôn ngữ: tiền tố `/en` của
  trang public (`findLocale`, kể cả request dữ liệu `/en.data`) → cookie `lng` → `Accept-Language`
  → `vi`. Trang riêng tư không có tiền tố ngôn ngữ. Bản dịch JSON đóng gói sẵn, namespace theo
  feature (`admin`, `audit`, `auth`, `chat`, `citations`, `collections`, `common`, `errors`,
  `landing`, `organizations`, `settings`); key có type; test bắt `vi` và `en` có cùng bộ key.
- **Theme**: remix-themes với cookie session; `ThemeProvider` + `PreventFlashOnWrongTheme`; action
  `/actions/theme`; không chọn gì nghĩa là theo hệ thống; trang prerender theo hệ thống.
- **Quy tắc giao diện**: mọi widget từ shadcn core (`base-nova`). Trước khi dựng gì, xem registry
  (`npx shadcn@latest view`), có thì `shadcn add` rồi sửa file CLI sinh ra; không gõ lại block thành
  component mới, không dùng registry thứ hai (không AI Elements), không thêm thư viện UI khi shadcn
  hoặc thư viện đã cài đáp ứng được. Ngoại lệ duy nhất: Tiptap và Streamdown. Bảng ánh xạ phần giao
  diện sang component shadcn và danh sách file `components/ui/` cố ý khác registry vì jsx-a11y nằm
  trong `frontend/README.md`, mục "UI components"; `shadcn add` muốn đè các file đó thì giữ bản local.
- Không có cảnh báo y khoa trong giao diện của agent.

## 9. Chất lượng và test

| Việc | Cấu hình |
| --- | --- |
| Gate mỗi thay đổi | `npm run lint && npm run format && npm run typecheck && npm test` trong `frontend/` |
| Lint, type | Oxlint type-aware, warning là lỗi, bỏ qua `node_modules/**`; TypeScript strict. Không `oxlint-disable`, `@ts-ignore`, `@ts-expect-error`; không ép kiểu `as T` (trừ `as const`) |
| Pre-commit ở root | `frontend-lint`, `frontend-format`, `frontend-typecheck`, `frontend-api-drift` |
| Unit (Node) | `app/**/*.test.ts(x)`: cite markers, chèn tin cũ, problem+json, CSRF, mapping message, i18n, cấu trúc kiến trúc |
| Browser (Chromium) | `app/**/*.browser.test.tsx` với MSW (`onUnhandledRequest: "error"`): chat dựng stream bằng `@shadcn/helpers`, cuộn tải tin cũ, citation, form tài khoản, tổ chức, collection, trình soạn thảo, admin. `console.error`/`console.warn` làm test fail |
| Contract | `ui-stream-contract` đọc fixture `.sse` của backend, kiểm từng chunk bằng schema của `ai` và render không lỗi |
| E2E | Playwright khởi động ba server: server E2E của backend (:8001, FastAPI thật, Postgres, Qdrant, LLM giả), bản build production của frontend (:3100), proxy một origin (:3200, `baseURL`). Spec: `account`, `admin`, `auth`, `chat`, `collections`, `organizations`, `public`, `settings` |

Ảnh Docker `frontend/Dockerfile` (nhiều stage trên `node:24-alpine`, chạy `react-router-serve` bằng
user không phải root, cổng 3000) dùng cho stack local qua `compose.yaml` (service `frontend` và
`nginx`, cấu hình `devops/nginx/conf.d/default.conf`) và là đường lùi nếu rời Vercel.

## 10. Ngoài phạm vi

- Trang corpus public, PWA, analytics.
- Tạo lại, sửa, rẽ nhánh câu trả lời (backend không hỗ trợ).
- Xác thực hai lớp, đăng nhập bằng nhà cung cấp khác Google.
- Biểu đồ trên trang admin khi chưa có endpoint thống kê theo thời gian.
- Skills của sản phẩm: đã bỏ hẳn (mục 11). URL `/skills` rơi vào trang 404.

## 11. Lịch sử quyết định

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-13 | React Router 8 framework mode, SSR cho trang public, trang riêng tư chỉ client | TanStack Start (còn RC), TanStack Router SPA (không SSR), Next.js | Người kế nhiệm Remix, stable, có SSR cho trang public sau này | `875eab98c6:frontend/docs/superpowers/specs/2026-09-13-frontend-v1-design.md` §17 |
| 2026-09-13 | AI SDK `useChat` + UI Message Stream, `MessageScroller` của shadcn | Runtime assistant-ui; LangGraph `useStream`; AI Elements | assistant-ui không phân trang history và không giữ vị trí khi chèn tin cũ; `useStream` cần LangGraph Server; AI Elements ghim `ai@6` | như trên |
| 2026-09-13 | orval sinh client, zod, MSW | @hey-api/openapi-ts (crash với TS 7), openapi-typescript + openapi-fetch | Stable, chạy với TS 7, có zod và mock | như trên |
| 2026-09-13 | Oxlint type-aware + Prettier, TypeScript 7 | Biome; ESLint (phải ở TS 6) | Lint type-aware stable trên TS 7; Prettier sắp class Tailwind 4 ổn định | như trên |
| 2026-09-13 | Cookie HttpOnly cùng origin + CSRF | BFF trong React Router; JWT trong `localStorage` | An toàn, cho phép SSR, thu hồi được phiên | như trên |
| 2026-09-13 | Base UI, i18next + remix-i18next, remix-themes, react-hook-form, Vitest, npm | Radix; Lingui, Paraglide; next-themes; TanStack Form; Jest; pnpm | Mặc định mới của shadcn; phổ biến, hỗ trợ middleware React Router 8; chạy thẳng trên Vite | như trên |
| 2026-09-13 | Bỏ `content-visibility: auto` trên item tin nhắn; chỉ tải tin cũ khi đã cuộn lên hoặc thread vừa khung | Tải trang cũ khi scroller báo chưa tới đầu | Bù vị trí khi chèn bị lệch cả khối; scroller báo `start: false` trước khi đo, gây tải thừa khi mở hội thoại | commit `078f1c9`, `dcc14d5` |
| 2026-09-16 | Bỏ trang `/skills`, feature `skills`, part `data-skills`, badge skill trong chat | Skills hệ thống và `SKILL.md` của người dùng (spec v1 §11) | Bỏ cả năng lực Skills của sản phẩm như chưa từng có | `875eab98c6:docs/superpowers/specs/2026-09-16-remove-product-skills-design.md`; commit `0efa031` |
| 2026-10-10 | Gộp `citations` vào `chat`; mọi feature có `components/`, `hooks/`, `lib/`; hướng import một chiều ép bằng lint và test | Feature `citations` riêng, import vòng với `chat` | Hai feature import lẫn nhau, citation chỉ hiện trong câu trả lời | commit `3e6e95f` |
| 2026-10-10 | Luồng tài khoản OTP: đăng ký, đăng nhập email hoặc số điện thoại, quên mật khẩu, quản lý email, số, Google, phiên trong cài đặt | v1 chỉ có email/mật khẩu, Google; cài đặt chỉ có tên và đổi mật khẩu; quên mật khẩu ngoài phạm vi | Đưa sản phẩm lên production | `d71e19237d:docs/superpowers/specs/2026-10-10-account-flows-design.md` §7 |
| 2026-10-10 | Tổ chức, collection, soạn tài liệu Tiptap, nhật ký, trang admin, trang pháp lý, nút Nguồn trong chat | Không có | Hoàn thiện sản phẩm để ra mắt | `d71e19237d:docs/superpowers/specs/2026-10-10-product-launch-design.md` §8 |
| 2026-10-10 | Chỉ dùng shadcn core; dựng lại các element chat bằng `alert`, `hover-card`, `item`, `toggle-group`; khung app và admin từ block `dashboard-01` | Element copy từ registry assistant-ui vào `app/components/elements/`; `PreviewCard` của Base UI cho xem trước citation; sidebar tự dựng | Một nguồn component, bớt code tự viết, đồng bộ style | spec ra mắt §8.1; commit `9e9eb47`, `4271fe7`, `004208d` |
| 2026-10-10 → 10-13 | Deploy frontend lên Vercel, route `api-proxy.ts` giữ một origin; không dùng preset `@vercel/react-router` | nginx + `react-router-serve` trên host riêng là đường chính | Miễn phí, không ngủ; preset làm hỏng build với React Router 8; proxy giữ cookie first-party | commit `ede81dc`, `64ae3f4`; spec ra mắt §9 |
| 2026-10-13 | Fetcher chỉ chạy trên trình duyệt; bỏ nhánh chuyển tiếp Cookie phía server; element chat dời vào `features/chat/components/elements/` | Fetcher có base URL nội bộ cho loader SSR (v1 §7.2) | Chưa trang public nào gọi API; code chết | commit `9e3763e` |
| 2026-10-15 | Citation chỉ còn một chunk; `CitationSheet` bỏ chiến lược hydrate và danh sách chunk | Sheet hiện "toàn bộ mục / đoạn và lân cận / một đoạn" với chunk `matched` tô nổi | Retrieval đọc chunk nguyên trạng (spec mảng 2) | commit `864126f` |

Ba plan cũ của frontend (`frontend-foundation`, `frontend-chat`, `frontend-skills-settings-e2e`)
đã chạy xong và bị xoá; đọc lại ở `875eab98c6:frontend/docs/superpowers/plans/<tên>.md`.

## 12. Liên kết

- `2026-11-15-backend-agent-api-design.md`: API web, UI Message Stream, fixture contract, server E2E.
- `2026-11-15-corpus-data-pipeline-design.md`: corpus, collection, chunk và citation.
- `2026-11-15-product-accounts-orgs-design.md`: tài khoản, OTP, tổ chức, quyền, hạn mức, xuất bản,
  deploy Vercel.
- `2026-11-15-architecture-rules-design.md`: quy tắc bố cục và ranh giới import của các project.
