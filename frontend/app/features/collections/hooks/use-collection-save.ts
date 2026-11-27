import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import {
  getCollectionsGetQueryKey,
  getCollectionsListQueryKey,
  useCollectionsUpdate,
} from "~/api/gen/endpoints"
import type { Visibility } from "~/api/gen/schemas"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"

/** Fields of a collection the owner can change from its page. */
export type CollectionChanges = { title?: string; visibility?: Visibility }

/**
 * Saves changes to one collection and refreshes its cached view and the
 * collection list. `saveAsync` rejects on failure so a form can show the
 * error; `save` reports it as a toast instead.
 */
export function useCollectionSave(collectionId: string) {
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const update = useCollectionsUpdate()
  const fail = (error: unknown) =>
    toast.add({ type: "error", title: apiErrorMessage(error, tErrors) })
  const saveAsync = async (data: CollectionChanges) => {
    const updated = await update.mutateAsync({ collectionId, data })
    queryClient.setQueryData(getCollectionsGetQueryKey(collectionId), updated)
    await queryClient.invalidateQueries({
      queryKey: getCollectionsListQueryKey(),
    })
  }
  const save = (data: CollectionChanges) => {
    void saveAsync(data).catch(fail)
  }
  return { save, saveAsync, fail, isPending: update.isPending }
}
