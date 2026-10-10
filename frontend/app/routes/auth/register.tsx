import { useTranslation } from "react-i18next"
import { Link, useSearchParams } from "react-router"

import { FieldSeparator } from "~/components/ui/field"
import { AuthCard } from "~/features/auth/components/AuthCard"
import { GoogleButton } from "~/features/auth/components/GoogleButton"
import { PhoneLoginForm } from "~/features/auth/components/PhoneLoginForm"
import { RegisterForm } from "~/features/auth/components/RegisterForm"
import { SignInMethods } from "~/features/auth/components/SignInMethods"
import { useRedirectIfAuthenticated } from "~/features/auth/hooks/use-redirect-if-authenticated"
import { safeNextPath } from "~/features/auth/lib/next-path"

export default function RegisterPage() {
  const { t } = useTranslation("auth")
  const [searchParams] = useSearchParams()
  const nextPath = safeNextPath(searchParams.get("next"))
  useRedirectIfAuthenticated(nextPath)

  return (
    <AuthCard
      title={t("register.title")}
      description={t("register.description")}
    >
      <title>{t("register.title")}</title>
      <SignInMethods
        email={<RegisterForm nextPath={nextPath} />}
        phone={<PhoneLoginForm nextPath={nextPath} intent="register" />}
      />
      <FieldSeparator>{t("or")}</FieldSeparator>
      <GoogleButton nextPath={nextPath} />
      <p className="text-center text-sm text-muted-foreground">
        {t("register.hasAccount")}{" "}
        <Link
          to={`/login?next=${encodeURIComponent(nextPath)}`}
          className="underline underline-offset-4"
        >
          {t("register.loginLink")}
        </Link>
      </p>
    </AuthCard>
  )
}
