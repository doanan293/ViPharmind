import { Fragment } from "react"

import type { SectionChoice } from "~/api/gen/schemas"
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  ComboboxValue,
  useComboboxAnchor,
} from "~/components/ui/combobox"

/** Searchable multi-select of the collection's document sections. */
export function SectionPicker({
  choices,
  value,
  onValueChange,
  label,
  empty,
  disabled = false,
}: {
  choices: readonly SectionChoice[]
  value: readonly string[]
  onValueChange: (keys: string[]) => void
  label: string
  empty: string
  disabled?: boolean
}) {
  const anchor = useComboboxAnchor()
  const selected = choices.filter((choice) => value.includes(choice.key))
  return (
    <Combobox
      multiple
      autoHighlight
      disabled={disabled}
      items={choices}
      value={selected}
      onValueChange={(next: SectionChoice[]) =>
        onValueChange(next.map((choice) => choice.key))
      }
      itemToStringLabel={(choice: SectionChoice) => choice.label}
      isItemEqualToValue={(item: SectionChoice, other: SectionChoice) =>
        item.key === other.key
      }
    >
      <ComboboxChips ref={anchor}>
        <ComboboxValue>
          {(values: SectionChoice[]) => (
            <Fragment>
              {values.map((choice) => (
                <ComboboxChip key={choice.key} showRemove={!disabled}>
                  {choice.label}
                </ComboboxChip>
              ))}
              <ComboboxChipsInput
                aria-label={label}
                placeholder={values.length === 0 ? label : undefined}
              />
            </Fragment>
          )}
        </ComboboxValue>
      </ComboboxChips>
      <ComboboxContent anchor={anchor}>
        <ComboboxEmpty>{empty}</ComboboxEmpty>
        <ComboboxList>
          {(choice: SectionChoice) => (
            <ComboboxItem key={choice.key} value={choice}>
              {choice.label}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
