import { useTranslation } from "react-i18next"

import type { AccountView } from "~/api/gen/schemas"
import { Separator } from "~/components/ui/separator"

import { ContactChangeFlow } from "./ContactChangeFlow"
import { GoogleSetting } from "./GoogleSetting"
import { SessionsList } from "./SessionsList"

export function AccountSection({ user }: { user: AccountView }) {
  const { t } = useTranslation("settings")
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.email.heading")}</h3>
        <ContactChangeFlow
          kind="email"
          current={user.email ?? null}
          verified={user.email_verified}
        />
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.phone.heading")}</h3>
        <ContactChangeFlow
          kind="phone"
          current={user.phone_number ?? null}
          verified={user.phone_verified}
        />
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.google.heading")}</h3>
        <GoogleSetting linked={user.google_linked} />
      </section>
      <Separator />
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("sessions.heading")}</h3>
        <SessionsList />
      </section>
    </div>
  )
}
