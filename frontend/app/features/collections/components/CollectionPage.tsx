import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getCollectionsListQueryKey,
  useCollectionsDelete,
  useCollectionsGet,
} from "~/api/gen/endpoints"
import { type CollectionView, Visibility } from "~/api/gen/schemas"
import { NameForm } from "~/components/name-form"
import { Alert, AlertDescription } from "~/components/ui/alert"
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
import { NativeSelect, NativeSelectOption } from "~/components/ui/native-select"
import { Spinner } from "~/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs"
import { apiErrorMessage } from "~/i18n/error-message"

import { useCollectionSave } from "../hooks/use-collection-save"
import { COLLECTION_TITLE_MAX_LENGTH } from "../lib/limits"
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

/** The tabs this collection shows and the one the URL selects among them. */
function tabsFor(
  collection: CollectionView,
  tab: string | undefined
): { tabs: readonly Tab[]; current: Tab } {
  const tabs: readonly Tab[] = collection.is_system ? ["releases"] : TABS
  const fallback: Tab = collection.is_system ? "releases" : "documents"
  return { tabs, current: tabs.find((name) => name === tab) ?? fallback }
}

function CollectionHeading({ collection }: { collection: CollectionView }) {
  const { t } = useTranslation("collections")
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold">{collection.title}</h1>
        {collection.is_system ? (
          <Badge variant="secondary">{t("list.system")}</Badge>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">{collection.owner_name}</p>
    </div>
  )
}

function CollectionActions({
  collectionId,
  collection,
  onRename,
  onDelete,
}: {
  collectionId: string
  collection: CollectionView
  onRename: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation("collections")
  const { save, isPending } = useCollectionSave(collectionId)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect
        aria-label={t("visibility.label")}
        value={collection.visibility}
        disabled={isPending}
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
      <Button variant="outline" onClick={onRename}>
        {t("actions.rename")}
      </Button>
      <Button variant="destructive" onClick={onDelete}>
        {t("actions.delete")}
      </Button>
    </div>
  )
}

function CollectionHeader({
  collectionId,
  collection,
  editable,
  onDelete,
}: {
  collectionId: string
  collection: CollectionView
  editable: boolean
  onDelete: () => void
}) {
  const { t } = useTranslation("collections")
  const { saveAsync } = useCollectionSave(collectionId)
  const [renaming, setRenaming] = useState(false)
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      {renaming ? (
        <NameForm
          id="collection-rename"
          field="title"
          label={t("list.titleLabel")}
          hideLabel
          defaultValue={collection.title}
          submitLabel={t("actions.save")}
          cancelLabel={t("actions.cancel")}
          requiredMessage={t("list.titleRequired")}
          maxLength={COLLECTION_TITLE_MAX_LENGTH}
          onCancel={() => setRenaming(false)}
          onSubmit={async (title) => {
            await saveAsync({ title })
            setRenaming(false)
          }}
        />
      ) : (
        <CollectionHeading collection={collection} />
      )}
      {editable && !renaming ? (
        <CollectionActions
          collectionId={collectionId}
          collection={collection}
          onRename={() => setRenaming(true)}
          onDelete={onDelete}
        />
      ) : (
        <Badge variant="outline">
          {t(`visibility.${collection.visibility}`)}
        </Badge>
      )}
    </div>
  )
}

function DeleteCollectionDialog({
  collectionId,
  open,
  onOpenChange,
}: {
  collectionId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation("collections")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const remove = useCollectionsDelete()
  const { fail } = useCollectionSave(collectionId)
  const confirm = () =>
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
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
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
            onClick={confirm}
          >
            {t("actions.deleteConfirm")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function CollectionTabs({
  collectionId,
  collection,
  editable,
  tab,
}: {
  collectionId: string
  collection: CollectionView
  editable: boolean
  tab: string | undefined
}) {
  const { t } = useTranslation("collections")
  const navigate = useNavigate()
  const { tabs, current } = tabsFor(collection, tab)
  return (
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
  )
}

/**
 * One collection's page: title, visibility and delete controls for editors,
 * and its documents, glossary, colloquial and release tabs. `tab` is the
 * route's tab segment; an unknown or missing value falls back to the first tab.
 */
export function CollectionPage({
  collectionId,
  tab,
}: {
  collectionId: string
  tab: string | undefined
}) {
  const { t: tErrors } = useTranslation("errors")
  const query = useCollectionsGet(collectionId)
  const [confirming, setConfirming] = useState(false)

  if (query.isError) {
    return (
      <Alert variant="destructive" className="m-4 w-auto md:m-8">
        <AlertDescription>
          {apiErrorMessage(query.error, tErrors)}
        </AlertDescription>
      </Alert>
    )
  }
  if (query.data === undefined) {
    return <Spinner />
  }
  const collection = query.data
  // The system corpus is built by pharma-lab, never authored here.
  const editable = collection.can_edit && !collection.is_system

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-4 md:p-8">
      <title>{collection.title}</title>
      <CollectionHeader
        collectionId={collectionId}
        collection={collection}
        editable={editable}
        onDelete={() => setConfirming(true)}
      />
      {editable ? <PublishButton collectionId={collectionId} /> : null}
      <CollectionTabs
        collectionId={collectionId}
        collection={collection}
        editable={editable}
        tab={tab}
      />
      <DeleteCollectionDialog
        collectionId={collectionId}
        open={confirming}
        onOpenChange={setConfirming}
      />
    </div>
  )
}
