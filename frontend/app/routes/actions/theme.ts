import { createThemeAction } from "remix-themes"

import { themeSessionResolver } from "~/lib/theme.server"

/**
 * Stores the theme the user picked in the theme session cookie; remix-themes posts here.
 */
export const action = createThemeAction(themeSessionResolver)
