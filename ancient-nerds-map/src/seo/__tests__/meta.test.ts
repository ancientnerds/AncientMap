/**
 * Byte-Parität gegen die eingefrorene Python-Referenz: meta.ts muss die
 * Heads reproduzieren, die der in Task 16 gelöschte Python-Renderer
 * einmalig nach pyref/ geschrieben hat (siehe fixtures.ts). Ändert sich
 * meta.ts bewusst, werden die pyref-Dateien von Hand mitgezogen und die
 * Abweichung im Commit begründet.
 *
 * Bewusste Abweichungen Python ↔ TypeScript — jede einzeln begründet:
 *
 *  1. <style>{SSR_CSS}</style>: Python bettet das SSR-CSS in jeden Head
 *     ein, weil die gesplicten Fragmente ohne das Bundle auskommen müssen.
 *     meta.ts bettet es NICHT ein — nach dem Cutover liefert das gebaute
 *     Vite-Bundle das CSS. stripSsrStyle() entfernt den Block vor dem
 *     Vergleich; darüber hinaus ist die Toleranz null.
 *
 * Mehr Abweichungen gibt es nicht. (renderHead maskiert < zusätzlich am
 * Sink; byte-identisch, weil jsonStr schon maskiert — Defense in Depth,
 * keine Ausgabedifferenz.)
 */

import { readdirSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import type { PageMeta } from '../meta'
import {
  articleIndexMeta,
  articleMeta,
  countryMeta,
  renderHead,
  researchIndexMeta,
  researchMeta,
  siteMeta,
  sitesIndexMeta,
  slugify,
  storyArchiveMeta,
  storyMeta,
} from '../meta'
import type { StoryRoute } from '../../types/anRoute'
import { FIXTURES, PYREF_DIR, pyrefHead, pyrefRoute } from './fixtures'

/** Bewusste Ausnahme 1: der SSR-CSS-Block (siehe Dateikommentar). */
const stripSsrStyle = (head: string) => head.replace(/\n<style>[\s\S]*?<\/style>/, '')

// Jeder pyref-Name → die Meta-Funktion, die ihn reproduzieren muss.
// Varianten decken Branches ab: story_short (leere Description seit
// b4690a3), storyArchive_page2 (Pager-Canonical), research_person
// (Person- statt Organization-Autor, kein Hero).
const PYREF_CASES: Record<string, (route: never) => PageMeta> = {
  story: storyMeta,
  story_short: storyMeta,
  storyArchive: storyArchiveMeta,
  storyArchive_page2: storyArchiveMeta,
  site: siteMeta,
  sitesIndex: sitesIndexMeta,
  country: countryMeta,
  research: researchMeta,
  research_person: researchMeta,
  researchIndex: researchIndexMeta,
  article: articleMeta,
  articleIndex: articleIndexMeta,
}

describe('Head-Gleichheit gegen die Python-Referenz', () => {
  it('die Referenz enthält den Style-Block, der bewusst gestrippt wird', () => {
    expect(pyrefHead('country')).toContain('<style>')
    expect(stripSsrStyle(pyrefHead('country'))).not.toContain('<style>')
  })

  it('jede pyref-Referenz wird verglichen — keine verwaisten Dateien', () => {
    const refs = readdirSync(PYREF_DIR)
      .filter(f => f.endsWith('.html'))
      .map(f => f.replace(/\.html$/, ''))
      .sort()
    expect(refs).toEqual(Object.keys(PYREF_CASES).sort())
  })

  it('die Referenz treibt </script> durch den JSON-LD-Pfad', () => {
    // story_short trägt </script> in der Headline: im Schema als \u003c
    // maskiert, im <title> HTML-escaped — nirgends als rohes </script>.
    const head = stripSsrStyle(pyrefHead('story_short'))
    expect(head).toContain('\\u003c/script>')
    expect(head).toContain('&lt;/script&gt;')
    expect(head.match(/<\/script>/g)).toHaveLength(1) // nur der JSON-LD-Schließtag
  })

  for (const [name, metaFn] of Object.entries(PYREF_CASES)) {
    it(`${name}: renderHead() == Python-Head minus <style>`, () => {
      const expected = stripSsrStyle(pyrefHead(name))
      const actual = renderHead(metaFn(pyrefRoute(name) as never))
      expect(actual).toBe(expected)
    })
  }
})

describe('slugify', () => {
  it('liefert denselben Slug wie die Python-Seite — Umlaute bleiben', () => {
    // Bis 2026-08-16 hatte ArticlesPage eine eigene ASCII-\w-Kopie, die
    // ö/ü strippte; Server-Slugs (article_html_renderer.slugify) behalten
    // sie. Sichtbar im country-pyref: der Server-Pfad enthält genau den
    // Slug, den diese Funktion liefert.
    expect(slugify('Göbekli Tepe')).toBe('göbekli-tepe')
    expect(FIXTURES.country.sites[0].path).toContain(slugify('Göbekli Tepe'))
  })
})

describe('countryMeta', () => {
  const m = countryMeta(FIXTURES.country)

  it('nennt Land und Anzahl im Title', () => {
    // Ohne Suffix: " | Ancient Nerds" hängt renderHead() an — und nur im
    // <title>, weil _meta_head() og:title/twitter:title unsuffigiert lässt.
    expect(m.title).toBe('Archaeological Sites in Türkiye (3)')
  })

  it('nennt die echten Typen und die Zeitspanne', () => {
    expect(m.description).toContain('temple complex, theatre and more')
    expect(m.description).toContain('Spanning 9600 BC – 155 AD')
  })

  it('kanonisiert prozentkodiert gegen die Apex-Domain', () => {
    expect(m.canonical).toBe('https://ancientnerds.com/sites/t%C3%BCrkiye')
  })

  it('nimmt einen echten Hero als og:image', () => {
    expect(m.image).toBe('https://ancientnerds.com/data/images/wiki/9c8b7a65/hero.webp')
  })
})

describe('storyMeta', () => {
  it('beschreibt aus post_text, nicht aus summary', () => {
    const m = storyMeta(FIXTURES.story)
    expect(m.description.startsWith('Archaeologists re-examined')).toBe(true)
    expect(m.description).not.toBe(FIXTURES.story.summary)
  })

  it('lässt die Description bei post_text < 150 Zeichen weg', () => {
    const m = storyMeta(pyrefRoute('story_short') as StoryRoute)
    expect(m.description).toBe('')
  })
})

describe('research-Autorschaft im JSON-LD (Art.-50-Fälle aus test_ai_act_notices.py)', () => {
  // Theo ist eine Pipeline, keine Person — das Schema darf nichts anderes
  // behaupten. Übernommen in Task 16, als der Python-Renderer starb.
  it('Theo wird eine Organization mit AI-Pipeline-Kennzeichnung', () => {
    expect(FIXTURES.research.author).toBe('Theo')
    const schema = JSON.parse(researchMeta(FIXTURES.research).schema!)
    expect(schema.author['@type']).toBe('Organization')
    expect(JSON.stringify(schema.author)).toContain('AI research pipeline')
    expect(JSON.stringify(schema)).not.toContain('"Person", "name": "Theo"')
  })

  it('ein menschlicher Autor bleibt eine Person', () => {
    const schema = JSON.parse(researchMeta(pyrefRoute('research_person') as never).schema!)
    expect(schema.author).toEqual({ '@type': 'Person', name: 'Dr. Jane Doe' })
  })

  it('ein Anführungszeichen im Namen kann das JSON nicht brechen', () => {
    const schema = JSON.parse(researchMeta({ ...FIXTURES.research, author: 'O"Brien' }).schema!)
    expect(schema.author.name).toBe('O"Brien')
  })

  // Art. 50(2): der IPTC-Marker kennzeichnet den TEXT der drei KI-generierten
  // Seitentypen maschinenlesbar. Kuratierte Seiten (site/country) tragen ihn
  // NICHT — dort ist der Inhalt nicht KI-generiert.
  const IPTC_AI_MARKER = 'https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia'

  it('story, research und journal tragen den IPTC-trainedAlgorithmicMedia-Marker', () => {
    for (const meta of [
      storyMeta(FIXTURES.story),
      researchMeta(FIXTURES.research),
      articleMeta(pyrefRoute('article') as never),
    ]) {
      expect(JSON.parse(meta.schema!).digitalSourceType).toBe(IPTC_AI_MARKER)
    }
  })

  it('kuratierte Seiten tragen keinen KI-Marker', () => {
    expect(siteMeta(pyrefRoute('site') as never).schema ?? '').not.toContain(IPTC_AI_MARKER)
    expect(countryMeta(pyrefRoute('country') as never).schema ?? '').not.toContain(IPTC_AI_MARKER)
  })
})

describe('renderHead', () => {
  it('erzeugt genau einen canonical und einen title', () => {
    const head = renderHead(countryMeta(FIXTURES.country))
    expect(head.match(/<link rel="canonical"/g)).toHaveLength(1)
    expect(head.match(/<title>/g)).toHaveLength(1)
  })

  it('suffigiert nur den <title>, nicht og:title/twitter:title', () => {
    const head = renderHead(countryMeta(FIXTURES.country))
    expect(head).toContain('<title>Archaeological Sites in Türkiye (3) | Ancient Nerds</title>')
    expect(head).toContain('<meta property="og:title" content="Archaeological Sites in Türkiye (3)">')
  })

  it('maskiert < in JSON-LD, damit kein script-Ausbruch möglich ist', () => {
    const head = renderHead({
      title: 'x',
      description: 'y',
      canonical: 'https://ancientnerds.com/x',
      schema: '{"n": "</script><b>"}',
    })
    expect(head).not.toContain('</script><b>')
  })
})

describe('leere Description (b4690a3: kein content="" ausliefern)', () => {
  it('lässt description/og:description/twitter:description komplett weg', () => {
    const head = renderHead({
      title: 'x',
      description: '',
      canonical: 'https://ancientnerds.com/x',
    })
    expect(head).not.toContain('name="description"')
    expect(head).not.toContain('property="og:description"')
    expect(head).not.toContain('name="twitter:description"')
    // Der Rest des Heads bleibt vollständig.
    expect(head).toContain('<title>x | Ancient Nerds</title>')
    expect(head).toContain('og:image')
  })

  it('nur-Whitespace zählt als leer', () => {
    const head = renderHead({
      title: 'x',
      description: '  \n\t ',
      canonical: 'https://ancientnerds.com/x',
    })
    expect(head).not.toContain('name="description"')
  })
})
