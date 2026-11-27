/** Milliseconds in one second, for converting between `Date.now()` and second counts. */
export const MILLISECONDS_PER_SECOND = 1000

/** Seconds in one day, the unit cookie `maxAge` values are built from. */
export const SECONDS_PER_DAY = 86_400

/** Days in a (non-leap) year. */
const DAYS_PER_YEAR = 365

/** Seconds in a 365-day year: the lifetime of the long-lived preference cookies. */
export const ONE_YEAR_SECONDS = SECONDS_PER_DAY * DAYS_PER_YEAR
