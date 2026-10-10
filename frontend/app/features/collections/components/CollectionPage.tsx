import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getCollectionsGetQueryKey,
  getCollectionsListQueryKey,
  useCollectionsDelete,
  useCollectionsGet,
  useCollectionsUpdate,
} from "~/api/gen/endpoints"
import { type CollectionView, Visibility } from "~/api/gen/schemas"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Input } from "~/components/ui/input"
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

import { ColloquialTab } from "./ColloquialTab"
import { DocumentsTab } from "./DocumentsTab"
import { GlossaryTab } from "./GlossaryTab"
import { PublishButton } from "./PublishButton"
import { ReleasesTab } from "./ReleasesTab"

const TABS = ["documents", "glossary", "colloquial", "releases"] as const
type Tab = (typeof TABS)[number]

/** Visibilities this viewer may pick; the current one always stays listed. */
function visibilityChoices(collection: CollectionView): Visibility[] {
  return Object.values(Visibility).filter(
    (value) =>
      value === collection.visibility ||
      value === "private" ||
      (value === "organization" && collection.owner_organization_id !== null) ||
      (value === "public" && collection.can_set_public)
  )
}

export function CollectionPage({
  collectionId,
  tab,
}: {
  collectionId: string
  tab: string | undefined
}) {
  const { t } = useTranslation("collections")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useCollectionsGet(collectionId)
  const update = useCollectionsUpdate()
  const remove = useCollectionsDelete()
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  if (query.isError) {
    return (
      <p role="alert" className="p-8 text-sm text-destructive">
        {apiErrorMessage(query.error, tErrors)}
      </p>
    )
  }
  if (query.data === undefined) {
    return <Spinner />
  }
  const collection = query.data
  // The system corpus is built by pharma-lab, never authored here.
  const editable = collection.can_edit && !collection.is_system
  const tabs: readonly Tab[] = collection.is_system ? ["releases"] : TABS
  const current: Tab =
    tabs.find((name) => name === tab) ??
    (collection.is_system ? "releases" : "documents")
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })
  const save = (data: { title?: string; visibility?: Visibility }) =>
    update.mutate(
      { collectionId, data },
      {
        onSuccess: (updated) => {
          queryClient.setQueryData(
            getCollectionsGetQueryKey(collectionId),
            updated
          )
          void queryClient.invalidateQueries({
            queryKey: getCollectionsListQueryKey(),
          })
          setRenaming(null)
        },
        onError: fail,
      }
    )

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 md:p-8">
      <title>{collection.title}</title>
      <div className="flex flex-wrap items-start justify-between gap-3">
        {renaming === null ? (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold">{collection.title}</h1>
              {collection.is_system ? (
                <Badge variant="secondary">{t("list.system")}</Badge>
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground">
              {collection.owner_name}
            </p>
          </div>
        ) : (
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              save({ title: renaming.trim() })
            }}
          >
            <Input
              aria-label={t("list.titleLabel")}
              value={renaming}
              maxLength={200}
              onChange={(event) => setRenaming(event.target.value)}
            />
            <Button type="submit" disabled={renaming.trim() === ""}>
              {t("actions.save")}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => setRenaming(null)}
            >
              {t("actions.cancel")}
            </Button>
          </form>
        )}
        {editable && renaming === null ? (
          <div className="flex flex-wrap items-center gap-2">
            <NativeSelect
              aria-label={t("visibility.label")}
              value={collection.visibility}
              disabled={update.isPending}
              onChange={(event) => {
                const visibility = Object.values(Visibility).find(
                  (value) => value === event.target.value
                )
                if (visibility !== undefined) save({ visibility })
              }}
            >
              {visibilityChoices(collection).map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {t(`visibility.${value}`)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <Button
              variant="outline"
              onClick={() => setRenaming(collection.title)}
            >
              {t("actions.rename")}
            </Button>
            <Button variant="destructive" onClick={() => setConfirming(true)}>
              {t("actions.delete")}
            </Button>
          </div>
        ) : (
          <Badge variant="outline">
            {t(`visibility.${collection.visibility}`)}
          </Badge>
        )}
      </div>
      {editable ? <PublishButton collectionId={collectionId} /> : null}
      <Tabs
        value={current}
        onValueChange={(value) =>
          void navigate(`/collections/${collectionId}/${String(value)}`)
        }
      >
        <TabsList>
          {tabs.map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        {collection.is_system ? null : (
          <>
            <TabsContent value="documents">
              <DocumentsTab collectionId={collectionId} editable={editable} />
            </TabsContent>
            <TabsContent value="glossary">
              <GlossaryTab collectionId={collectionId} editable={editable} />
            </TabsContent>
            <TabsContent value="colloquial">
              <ColloquialTab collectionId={collectionId} editable={editable} />
            </TabsContent>
          </>
        )}
        <TabsContent value="releases">
          <ReleasesTab collectionId={collectionId} editable={editable} />
        </TabsContent>
      </Tabs>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("actions.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("actions.deleteDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("actions.cancel")}</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(
                  { collectionId },
                  {
                    onSuccess: () => {
                      void queryClient.invalidateQueries({
                        queryKey: getCollectionsListQueryKey(),
                      })
                      void navigate("/collections", { replace: true })
                    },
                    onError: fail,
                  }
                )
              }
            >
              {t("actions.deleteConfirm")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
