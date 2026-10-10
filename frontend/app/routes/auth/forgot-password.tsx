import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { AuthCard } from "~/features/auth/components/AuthCard"
import { ForgotPasswordForm } from "~/features/auth/components/ForgotPasswordForm"

export default function ForgotPasswordPage() {
  const { t } = useTranslation("auth")
  return (
    <AuthCard title={t("forgot.title")} description={t("forgot.description")}>
      <title>{t("forgot.title")}</title>
      <ForgotPasswordForm />
      <p className="text-center text-sm text-muted-foreground">
        <Link to="/login" className="underline underline-offset-4">
          {t("register.loginLink")}
        </Link>
      </p>
    </AuthCard>
  )
}
