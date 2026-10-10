import { useParams } from "react-router"

import { CollectionPage } from "~/features/collections/components/CollectionPage"

export default function CollectionRoute() {
  const { collectionId = "", tab } = useParams()
  return (
    <CollectionPage key={collectionId} collectionId={collectionId} tab={tab} />
  )
}
