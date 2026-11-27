import { useParams } from "react-router"

import { DocumentEditorPage } from "~/features/collections/components/DocumentEditorPage"

/** The document editor; the document id `new` opens an empty document in the collection. */
export default function DocumentRoute() {
  const { collectionId = "", documentId = "new" } = useParams()
  return (
    <DocumentEditorPage
      key={`${collectionId}/${documentId}`}
      collectionId={collectionId}
      documentId={documentId}
    />
  )
}
