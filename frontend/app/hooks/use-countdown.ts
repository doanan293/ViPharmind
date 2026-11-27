import { useCallback, useEffect, useState } from "react"

import { MILLISECONDS_PER_SECOND } from "~/lib/time"

/** Whole seconds left until a deadline set with `start`; 0 when idle. */
export function useCountdown(): {
  secondsLeft: number
  start: (seconds: number) => void
} {
  const [deadline, setDeadline] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (deadline === null) {
      return undefined
    }
    const timer = window.setInterval(() => {
      const current = Date.now()
      setNow(current)
      if (current >= deadline) {
        setDeadline(null)
      }
    }, MILLISECONDS_PER_SECOND)
    return () => {
      window.clearInterval(timer)
    }
  }, [deadline])

  const start = useCallback((seconds: number) => {
    const current = Date.now()
    setNow(current)
    setDeadline(current + seconds * MILLISECONDS_PER_SECOND)
  }, [])

  const secondsLeft =
    deadline === null
      ? 0
      : Math.max(0, Math.ceil((deadline - now) / MILLISECONDS_PER_SECOND))
  return { secondsLeft, start }
}
