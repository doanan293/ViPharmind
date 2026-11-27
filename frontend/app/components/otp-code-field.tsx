import { REGEXP_ONLY_DIGITS } from "input-otp"

import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "~/components/ui/input-otp"

/** How many digits a one-time code has; the backend sends codes of this length. */
export const OTP_LENGTH = 6

/** Slot positions 0..OTP_LENGTH-1; a slot's position is its identity. */
const SLOT_POSITIONS = Array.from(
  { length: OTP_LENGTH },
  (_, position) => position
)

/**
 * The digit-only input for a one-time code, one box per digit, with `autocomplete=one-time-code`
 * so phones offer the SMS code. Controlled: the caller owns `value`.
 */
export function OtpCodeField({
  id,
  value,
  onChange,
  invalid = false,
  disabled = false,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  invalid?: boolean
  disabled?: boolean
}) {
  return (
    <InputOTP
      id={id}
      maxLength={OTP_LENGTH}
      pattern={REGEXP_ONLY_DIGITS}
      inputMode="numeric"
      autoComplete="one-time-code"
      value={value}
      onChange={onChange}
      disabled={disabled}
      aria-invalid={invalid}
    >
      <InputOTPGroup>
        {SLOT_POSITIONS.map((position) => (
          <InputOTPSlot key={position} index={position} />
        ))}
      </InputOTPGroup>
    </InputOTP>
  )
}
