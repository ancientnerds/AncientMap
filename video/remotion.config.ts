import { Config } from '@remotion/cli/config'

// Settings for `npm run studio` (the preview) only: scripts/render.ts, lint.ts
// and still.ts pass every render option explicitly.
Config.setVideoImageFormat('jpeg')
Config.setOverwriteOutput(true)
