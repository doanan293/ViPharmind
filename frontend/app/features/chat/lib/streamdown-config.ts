import { code } from "@streamdown/code"
import { math } from "@streamdown/math"
import type { PluginConfig } from "streamdown"

/** The Streamdown plugins for answers and cited passages: code highlighting and math. */
export const streamdownPlugins: PluginConfig = { code, math }
