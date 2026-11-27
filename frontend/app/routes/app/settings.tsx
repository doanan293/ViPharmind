import { LegalLinks } from "~/features/legal/components/LegalLinks"
import { SettingsPage } from "~/features/settings/components/SettingsPage"

/** Account settings at `/settings`, followed by links to the legal pages. */
export default function SettingsRoute() {
  return (
    <>
      <SettingsPage />
      <div className="mx-auto w-full max-w-2xl px-4 pb-8 md:px-8">
        <LegalLinks />
      </div>
    </>
  )
}
