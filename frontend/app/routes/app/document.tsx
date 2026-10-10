import { useParams } from "react-router"

import { DocumentEditorPage } from "~/features/collections/components/DocumentEditorPage"

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
