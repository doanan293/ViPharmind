import {
  type ColumnDef,
  type ColumnVisibilityState,
  type RowData,
  type SortingState,
  FlexRender,
  columnVisibilityFeature,
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table"
import {
  ArrowDownIcon,
  ArrowUpDownIcon,
  ArrowUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  Columns3Icon,
} from "lucide-react"
import * as React from "react"
import { useTranslation } from "react-i18next"

import { Button } from "~/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import { Label } from "~/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"

/*
 * The data table of shadcn's dashboard-01 block (installed with `shadcn add dashboard-01`),
 * made generic: callers pass columns and rows. The block's row drag, row selection, demo
 * tabs and detail drawer are removed; sorting, the column picker and pagination stay.
 */
export const dataTableFeatures = tableFeatures({
  columnVisibilityFeature,
  rowPaginationFeature,
  rowSortingFeature,
  paginatedRowModel: createPaginatedRowModel(),
  sortedRowModel: createSortedRowModel(),
})

export type DataTableFeatures = typeof dataTableFeatures

export function dataTableColumns<TData extends RowData>() {
  return createColumnHelper<DataTableFeatures, TData>()
}

const PAGE_SIZES = [10, 20, 50, 100]

function columnLabel(
  column: { id: string; columnDef: { header?: unknown } },
  labels: Readonly<Record<string, string>>
): string {
  const header = column.columnDef.header
  return labels[column.id] ?? (typeof header === "string" ? header : column.id)
}

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") return <ArrowUpIcon data-icon="inline-end" />
  if (sorted === "desc") return <ArrowDownIcon data-icon="inline-end" />
  return <ArrowUpDownIcon data-icon="inline-end" className="opacity-40" />
}

export function DataTable<TData extends RowData>({
  data,
  columns,
  getRowId,
  columnLabels = {},
  toolbar,
  footer,
}: {
  data: TData[]
  columns: ColumnDef<DataTableFeatures, TData>[]
  getRowId: (row: TData) => string
  /** Translated column names for the column picker and sort buttons, by column id. */
  columnLabels?: Readonly<Record<string, string>>
  /** Left of the column picker, such as a search field. */
  toolbar?: React.ReactNode
  /** Under the pagination, such as a "load more" button for server pages. */
  footer?: React.ReactNode
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  const sizeId = React.useId()
  const [columnVisibility, setColumnVisibility] =
    React.useState<ColumnVisibilityState>({})
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: 20,
  })
  const table = useTable({
    features: dataTableFeatures,
    data,
    columns,
    state: { sorting, columnVisibility, pagination },
    getRowId,
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: setPagination,
  })

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-1 items-center gap-2">{toolbar}</div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>
            <Columns3Icon data-icon="inline-start" />
            {t("columns")}
            <ChevronDownIcon data-icon="inline-end" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            {table
              .getAllColumns()
              .filter((column) => column.getCanHide())
              .map((column) => {
                return (
                  <DropdownMenuCheckboxItem
                    key={column.id}
                    checked={column.getIsVisible()}
                    onCheckedChange={(value) => column.toggleVisibility(value)}
                  >
                    {columnLabel(column, columnLabels)}
                  </DropdownMenuCheckboxItem>
                )
              })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="relative flex flex-col gap-4">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-muted">
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => {
                    return (
                      <TableHead key={header.id} colSpan={header.colSpan}>
                        {header.isPlaceholder ? null : header.column.getCanSort() ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="-ml-2"
                            aria-label={t("sortBy", {
                              column: columnLabel(header.column, columnLabels),
                            })}
                            onClick={header.column.getToggleSortingHandler()}
                          >
                            <FlexRender header={header} />
                            <SortIcon sorted={header.column.getIsSorted()} />
                          </Button>
                        ) : (
                          <FlexRender header={header} />
                        )}
                      </TableHead>
                    )
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length > 0 ? (
                table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        <FlexRender cell={cell} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="h-24 text-center"
                  >
                    {t("empty")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="flex items-center justify-between px-4">
          <div className="hidden flex-1 lg:flex" />
          <div className="flex w-full items-center gap-8 lg:w-fit">
            <div className="hidden items-center gap-2 lg:flex">
              <Label htmlFor={sizeId} className="text-sm font-medium">
                {t("rowsPerPage")}
              </Label>
              <Select
                value={String(table.state.pagination.pageSize)}
                onValueChange={(value) => {
                  table.setPageSize(Number(value))
                }}
                items={PAGE_SIZES.map((pageSize) => ({
                  label: String(pageSize),
                  value: String(pageSize),
                }))}
              >
                <SelectTrigger size="sm" className="w-20" id={sizeId}>
                  <SelectValue placeholder={table.state.pagination.pageSize} />
                </SelectTrigger>
                <SelectContent side="top">
                  <SelectGroup>
                    {PAGE_SIZES.map((pageSize) => (
                      <SelectItem key={pageSize} value={String(pageSize)}>
                        {pageSize}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex w-fit items-center justify-center text-sm font-medium">
              {t("page", {
                page: table.state.pagination.pageIndex + 1,
                count: Math.max(table.getPageCount(), 1),
              })}
            </div>
            <div className="ml-auto flex items-center gap-2 lg:ml-0">
              <Button
                variant="outline"
                className="hidden h-8 w-8 p-0 lg:flex"
                onClick={() => table.setPageIndex(0)}
                disabled={!table.getCanPreviousPage()}
              >
                <span className="sr-only">{t("first")}</span>
                <ChevronsLeftIcon />
              </Button>
              <Button
                variant="outline"
                className="size-8"
                size="icon"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}
              >
                <span className="sr-only">{t("previous")}</span>
                <ChevronLeftIcon />
              </Button>
              <Button
                variant="outline"
                className="size-8"
                size="icon"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}
              >
                <span className="sr-only">{t("next")}</span>
                <ChevronRightIcon />
              </Button>
              <Button
                variant="outline"
                className="hidden size-8 lg:flex"
                size="icon"
                onClick={() => table.setPageIndex(table.getPageCount() - 1)}
                disabled={!table.getCanNextPage()}
              >
                <span className="sr-only">{t("last")}</span>
                <ChevronsRightIcon />
              </Button>
            </div>
          </div>
        </div>
      </div>
      {footer}
    </div>
  )
}
