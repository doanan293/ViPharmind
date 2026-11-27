import { useParams } from "react-router"

import { CollectionPage } from "~/features/collections/components/CollectionPage"

/**
 * One collection at `/collections/:collectionId/:tab?`; the page remounts when the
 * collection changes.
 */
export default function CollectionRoute() {
  const { collectionId = "", tab } = useParams()
  return (
    <CollectionPage key={collectionId} collectionId={collectionId} tab={tab} />
  )
}
