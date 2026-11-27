import {
  type ColumnDef,
  type ColumnVisibilityState,
  columnVisibilityFeature,
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  FlexRender,
  type ReactTable,
  type RowData,
  rowPaginationFeature,
  rowSortingFeature,
  type SortingState,
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
const dataTableFeatures = tableFeatures({
  columnVisibilityFeature,
  rowPaginationFeature,
  rowSortingFeature,
  paginatedRowModel: createPaginatedRowModel(),
  sortedRowModel: createSortedRowModel(),
})

type DataTableFeatures = typeof dataTableFeatures

type DataTableInstance<TData extends RowData> = ReactTable<
  DataTableFeatures,
  TData
>

type ColumnLabels = Readonly<Record<string, string>>

/**
 * The column helper typed for `DataTable`'s features; build a table's `columns` with it so
 * they type-check against `DataTable`.
 */
export function dataTableColumns<TData extends RowData>() {
  return createColumnHelper<DataTableFeatures, TData>()
}

const MIN_PAGE_SIZE = 10
const DEFAULT_PAGE_SIZE = 20
const LARGE_PAGE_SIZE = 50
const MAX_PAGE_SIZE = 100
const PAGE_SIZES = [
  MIN_PAGE_SIZE,
  DEFAULT_PAGE_SIZE,
  LARGE_PAGE_SIZE,
  MAX_PAGE_SIZE,
]

function columnLabel(
  column: { id: string; columnDef: { header?: unknown } },
  labels: ColumnLabels
): string {
  const header = column.columnDef.header
  return labels[column.id] ?? (typeof header === "string" ? header : column.id)
}

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") return <ArrowUpIcon data-icon="inline-end" />
  if (sorted === "desc") return <ArrowDownIcon data-icon="inline-end" />
  return <ArrowUpDownIcon data-icon="inline-end" className="opacity-40" />
}

/** The dropdown that shows or hides the columns that can be hidden. */
function ColumnPicker<TData extends RowData>({
  table,
  columnLabels,
}: {
  table: DataTableInstance<TData>
  columnLabels: ColumnLabels
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  return (
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
  )
}

/** The header row: sortable columns get a button that cycles the sort order. */
function DataTableHeader<TData extends RowData>({
  table,
  columnLabels,
}: {
  table: DataTableInstance<TData>
  columnLabels: ColumnLabels
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  return (
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
  )
}

/** The rows of the current page, or one "empty" row spanning every column. */
function DataTableBody<TData extends RowData>({
  table,
  columnCount,
}: {
  table: DataTableInstance<TData>
  columnCount: number
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  return (
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
          <TableCell colSpan={columnCount} className="h-24 text-center">
            {t("empty")}
          </TableCell>
        </TableRow>
      )}
    </TableBody>
  )
}

/** The "rows per page" select, shown from the `lg` breakpoint up. */
function PageSizeSelect<TData extends RowData>({
  table,
}: {
  table: DataTableInstance<TData>
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  const sizeId = React.useId()
  return (
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
  )
}

/** First, previous, next and last page buttons; first and last show from `lg` up. */
function PageButtons<TData extends RowData>({
  table,
}: {
  table: DataTableInstance<TData>
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  return (
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
  )
}

/** The bar under the table: page size, "page x of y" and the page buttons. */
function DataTablePagination<TData extends RowData>({
  table,
}: {
  table: DataTableInstance<TData>
}) {
  const { t } = useTranslation("common", { keyPrefix: "table" })
  return (
    <div className="flex items-center justify-between px-4">
      <div className="hidden flex-1 lg:flex" />
      <div className="flex w-full items-center gap-8 lg:w-fit">
        <PageSizeSelect table={table} />
        <div className="flex w-fit items-center justify-center text-sm font-medium">
          {t("page", {
            page: table.state.pagination.pageIndex + 1,
            count: Math.max(table.getPageCount(), 1),
          })}
        </div>
        <PageButtons table={table} />
      </div>
    </div>
  )
}

/**
 * The data table of shadcn's dashboard-01 block with client-side sorting, a column picker
 * and pagination over `data`. Build `columns` with `dataTableColumns`; `getRowId` must give
 * each row a stable id.
 */
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
  columnLabels?: ColumnLabels
  /** Left of the column picker, such as a search field. */
  toolbar?: React.ReactNode
  /** Under the pagination, such as a "load more" button for server pages. */
  footer?: React.ReactNode
}) {
  const [columnVisibility, setColumnVisibility] =
    React.useState<ColumnVisibilityState>({})
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: DEFAULT_PAGE_SIZE,
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
        <ColumnPicker table={table} columnLabels={columnLabels} />
      </div>
      <div className="relative flex flex-col gap-4">
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <DataTableHeader table={table} columnLabels={columnLabels} />
            <DataTableBody table={table} columnCount={columns.length} />
          </Table>
        </div>
        <DataTablePagination table={table} />
      </div>
      {footer}
    </div>
  )
}
