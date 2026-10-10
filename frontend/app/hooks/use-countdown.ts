import { useCallback, useEffect, useState } from "react"

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
    }, 1000)
    return () => {
      window.clearInterval(timer)
    }
  }, [deadline])

  const start = useCallback((seconds: number) => {
    const current = Date.now()
    setNow(current)
    setDeadline(current + seconds * 1000)
  }, [])

  const secondsLeft =
    deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000))
  return { secondsLeft, start }
}
