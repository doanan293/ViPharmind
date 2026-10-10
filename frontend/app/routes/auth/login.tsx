import { useTranslation } from "react-i18next"
import { Link, useSearchParams } from "react-router"

import { FieldSeparator } from "~/components/ui/field"
import { AuthCard } from "~/features/auth/components/AuthCard"
import { GoogleButton } from "~/features/auth/components/GoogleButton"
import { LoginForm } from "~/features/auth/components/LoginForm"
import { PhoneLoginForm } from "~/features/auth/components/PhoneLoginForm"
import { SignInMethods } from "~/features/auth/components/SignInMethods"
import { useRedirectIfAuthenticated } from "~/features/auth/hooks/use-redirect-if-authenticated"
import { safeNextPath } from "~/features/auth/lib/next-path"
import { isErrorCode } from "~/i18n/error-message"

export default function LoginPage() {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const [searchParams] = useSearchParams()
  const nextPath = safeNextPath(searchParams.get("next"))
  const errorCode = searchParams.get("error")
  useRedirectIfAuthenticated(nextPath)

  return (
    <AuthCard title={t("login.title")} description={t("login.description")}>
      <title>{t("login.title")}</title>
      {errorCode === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {tErrors(isErrorCode(errorCode) ? errorCode : "UNKNOWN")}
        </p>
      )}
      <SignInMethods
        email={
          <>
            <LoginForm nextPath={nextPath} />
            <Link
              to="/forgot-password"
              className="text-sm underline underline-offset-4"
            >
              {t("login.forgotLink")}
            </Link>
          </>
        }
        phone={<PhoneLoginForm nextPath={nextPath} />}
      />
      <FieldSeparator>{t("or")}</FieldSeparator>
      <GoogleButton nextPath={nextPath} />
      <p className="text-center text-sm text-muted-foreground">
        {t("login.noAccount")}{" "}
        <Link
          to={`/register?next=${encodeURIComponent(nextPath)}`}
          className="underline underline-offset-4"
        >
          {t("login.registerLink")}
        </Link>
      </p>
    </AuthCard>
  )
}
