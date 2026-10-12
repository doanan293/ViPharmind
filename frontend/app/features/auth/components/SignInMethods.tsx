import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs"
import { useSignInOptions } from "~/features/auth/hooks/use-sign-in-options"

/** Email and phone tabs; phone only once the server says SMS is on. */
export function SignInMethods({
  email,
  phone,
}: {
  email: ReactNode
  phone: ReactNode
}) {
  const { t } = useTranslation("auth")
  const options = useSignInOptions()
  if (!options.phone) {
    return <div className="flex flex-col gap-4">{email}</div>
  }
  return (
    <Tabs defaultValue="email" className="flex flex-col gap-6">
      <TabsList className="w-full">
        <TabsTrigger value="email">{t("tabs.email")}</TabsTrigger>
        <TabsTrigger value="phone">{t("tabs.phone")}</TabsTrigger>
      </TabsList>
      <TabsContent value="email" className="flex flex-col gap-4">
        {email}
      </TabsContent>
      <TabsContent value="phone">{phone}</TabsContent>
    </Tabs>
  )
}
