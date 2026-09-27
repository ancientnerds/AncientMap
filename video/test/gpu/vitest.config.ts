/**
 * The real-browser checks under test/gpu (`npm run test:gpu`, cwd video/). They
 * render in Remotion's Chrome on the RTX 3080 (spec 4.11), so they run on the
 * workstation only. The CI job lint-video runs `npm test`, whose config
 * (video/vitest.config.ts) collects only files named *.test.ts, never these
 * *.gpu.ts files.
 */
import { fileURLToPath } from 'node:url'

import { defineConfig } from 'vitest/config'

export default defineConfig({
  root: fileURLToPath(new URL('../..', import.meta.url)),
  test: {
    include: ['test/gpu/**/*.gpu.ts'],
    environment: 'node',
    fileParallelism: false,
  },
})
