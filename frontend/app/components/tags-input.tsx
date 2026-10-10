import { Fragment, useState } from "react"

import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxItem,
  ComboboxList,
  ComboboxValue,
  useComboboxAnchor,
} from "~/components/ui/combobox"

/**
 * Free-form list of short values as shadcn combobox chips: type a value and press Enter to
 * add it, remove a chip with its × button.
 */
export function TagsInput({
  value,
  onValueChange,
  label,
  placeholder,
  disabled = false,
}: {
  value: readonly string[]
  onValueChange: (value: string[]) => void
  label: string
  placeholder?: string
  disabled?: boolean
}) {
  const anchor = useComboboxAnchor()
  const [typed, setTyped] = useState("")
  const candidate = typed.trim()
  const items = candidate === "" || value.includes(candidate) ? [] : [candidate]

  return (
    <Combobox
      multiple
      autoHighlight
      disabled={disabled}
      items={items}
      value={[...value]}
      onValueChange={(next: string[]) => {
        onValueChange(next)
        setTyped("")
      }}
      inputValue={typed}
      onInputValueChange={setTyped}
    >
      <ComboboxChips ref={anchor}>
        <ComboboxValue>
          {(values: string[]) => (
            <Fragment>
              {values.map((item) => (
                <ComboboxChip key={item} showRemove={!disabled}>
                  {item}
                </ComboboxChip>
              ))}
              <ComboboxChipsInput
                aria-label={label}
                placeholder={values.length === 0 ? placeholder : undefined}
              />
            </Fragment>
          )}
        </ComboboxValue>
      </ComboboxChips>
      {items.length === 0 ? null : (
        <ComboboxContent anchor={anchor}>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item}>
                {item}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      )}
    </Combobox>
  )
}
