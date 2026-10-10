import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { useAdminCollectionsList } from "~/api/gen/endpoints"
import { Badge } from "~/components/ui/badge"
import { Empty, EmptyDescription, EmptyHeader } from "~/components/ui/empty"
import { Spinner } from "~/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"

/** Every collection with its size in Postgres and Qdrant, to spot drift and heavy users. */
export function CollectionsSection() {
  const { t, i18n } = useTranslation("admin")
  const { t: tCollections } = useTranslation("collections")
  const stats = useAdminCollectionsList()
  const numbers = new Intl.NumberFormat(i18n.language)
  if (stats.data === undefined) return <Spinner />
  if (stats.data.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyDescription>{t("collections.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("collections.title")}</TableHead>
          <TableHead>{t("collections.owner")}</TableHead>
          <TableHead>{t("collections.visibility")}</TableHead>
          <TableHead className="text-right">
            {t("collections.documents")}
          </TableHead>
          <TableHead className="text-right">
            {t("collections.points")}
          </TableHead>
          <TableHead className="text-right">
            {t("collections.release")}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {stats.data.map(({ collection, documents, qdrant_points }) => (
          <TableRow key={collection.id}>
            <TableCell>
              <Link
                to={`/collections/${collection.id}`}
                className="font-medium underline-offset-4 hover:underline"
              >
                {collection.title}
              </Link>
            </TableCell>
            <TableCell>{collection.owner_name}</TableCell>
            <TableCell>
              <Badge variant="outline">
                {tCollections(`visibility.${collection.visibility}`)}
              </Badge>
            </TableCell>
            <TableCell className="text-right">
              {numbers.format(documents)}
            </TableCell>
            <TableCell className="text-right">
              {numbers.format(qdrant_points)}
            </TableCell>
            <TableCell className="text-right">
              {collection.current_release_number ?? "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
