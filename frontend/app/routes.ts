import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes"

export default [
  index("routes/public/landing.tsx", { id: "landing-vi" }),
  route("en", "routes/public/landing.tsx", { id: "landing-en" }),
  route("privacy", "routes/public/privacy.tsx", { id: "privacy-vi" }),
  route("en/privacy", "routes/public/privacy.tsx", { id: "privacy-en" }),
  route("terms", "routes/public/terms.tsx", { id: "terms-vi" }),
  route("en/terms", "routes/public/terms.tsx", { id: "terms-en" }),
  route("login", "routes/auth/login.tsx"),
  route("register", "routes/auth/register.tsx"),
  route("forgot-password", "routes/auth/forgot-password.tsx"),
  route("auth/google/callback", "routes/auth/google-callback.tsx"),
  route("auth/google/link-callback", "routes/auth/google-link-callback.tsx"),
  route("invitations/:token", "routes/public/invitation.tsx"),
  layout("routes/app/layout.tsx", [
    route("chat/:conversationId?", "routes/app/chat.tsx"),
    route("settings", "routes/app/settings.tsx"),
    route("activity", "routes/app/activity.tsx"),
    route("organizations", "routes/app/organizations.tsx"),
    route("organizations/:organizationId/:tab?", "routes/app/organization.tsx"),
    route("collections", "routes/app/collections.tsx"),
    route("admin/:section?", "routes/app/admin.tsx"),
    route(
      "collections/:collectionId/documents/:documentId",
      "routes/app/document.tsx"
    ),
    route("collections/:collectionId/:tab?", "routes/app/collection.tsx"),
  ]),
  route("api/*", "routes/api-proxy.ts"),
  route("actions/locale", "routes/actions/locale.ts"),
  route("actions/theme", "routes/actions/theme.ts"),
  route("*", "routes/not-found.tsx"),
] satisfies RouteConfig
