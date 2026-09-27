/**
 * Brand fonts from the per-render public dir. pipeline/studio/render.py links
 * every ancient-nerds-map/public/fonts/*.woff2 into <episode>/render/public/fonts;
 * `npm run studio` points --public-dir at ancient-nerds-map/public directly.
 * loadFont() holds the render (delayRender) until each file is loaded and fails
 * it when a file is missing; scripts/cli.ts checks the files before Chrome starts.
 *
 * Each face carries the unicode-range of the site's fonts.css (glyphs.ts): the
 * latin files, plus the latin-ext files of JetBrains Mono (both weights share the
 * 400 file, as on the site) and Cormorant Garamond. Orbitron ships latin only, so
 * HEADING names JetBrains Mono second: a latin-ext character of a heading is drawn
 * by the JetBrains Mono latin-ext face, never by a system font.
 */
import { loadFont } from '@remotion/fonts'
import { staticFile } from 'remotion'

import { LATIN_EXT_RANGE, LATIN_RANGE } from './glyphs'

export const FONTS = [
  { family: 'Orbitron', file: 'fonts/orbitron-600.woff2', weight: '600', unicodeRange: LATIN_RANGE },
  { family: 'Orbitron', file: 'fonts/orbitron-700.woff2', weight: '700', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400.woff2', weight: '400', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400-latin-ext.woff2', weight: '400', unicodeRange: LATIN_EXT_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-500.woff2', weight: '500', unicodeRange: LATIN_RANGE },
  { family: 'JetBrains Mono', file: 'fonts/jetbrains-mono-400-latin-ext.woff2', weight: '500', unicodeRange: LATIN_EXT_RANGE },
  { family: 'Cormorant Garamond', file: 'fonts/cormorant-garamond-400-latin.woff2', weight: '400', unicodeRange: LATIN_RANGE },
  { family: 'Cormorant Garamond', file: 'fonts/cormorant-garamond-400-latin-ext.woff2', weight: '400', unicodeRange: LATIN_EXT_RANGE },
] as const

/** The seven distinct files the public dir must hold (JetBrains Mono's latin-ext file serves both weights). */
export const FONT_FILES: readonly string[] = [...new Set(FONTS.map((f) => f.file))]

export const HEADING = "'Orbitron', 'JetBrains Mono', sans-serif"
export const BODY = "'JetBrains Mono', monospace"
/** Verbatim passages of old texts (QuoteCard), the site's serif. */
export const SERIF = "'Cormorant Garamond', serif"

export function loadBrandFonts(): void {
  for (const font of FONTS) {
    void loadFont({ family: font.family, url: staticFile(font.file), weight: font.weight, unicodeRange: font.unicodeRange })
  }
}
