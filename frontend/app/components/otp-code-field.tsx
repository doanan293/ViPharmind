import { REGEXP_ONLY_DIGITS } from "input-otp"

import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "~/components/ui/input-otp"

export const OTP_LENGTH = 6

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
        {Array.from({ length: OTP_LENGTH }, (_, index) => (
          <InputOTPSlot key={index} index={index} />
        ))}
      </InputOTPGroup>
    </InputOTP>
  )
}
