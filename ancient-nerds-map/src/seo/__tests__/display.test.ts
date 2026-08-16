/**
 * Portierungstests für display.ts — _coord_display()/_period_display() aus
 * pipeline/sites_html_renderer.py sind die Vorlage (react-ssr Task 11).
 * Einzige bewusste Abweichung: ° statt der HTML-Entität &deg;, weil React
 * Text escapet, während der Python-Body ungeescaped eingesetzt wurde.
 */

import { describe, expect, it } from 'vitest'

import { coordDisplay, longDate, periodDisplay } from '../display'

describe('coordDisplay', () => {
  it('formatiert Nord/Ost mit vier Nachkommastellen', () => {
    expect(coordDisplay(37.2231, 38.9224)).toBe('37.2231° N, 38.9224° E')
  })

  it('padded kurze Werte wie Pythons :.4f', () => {
    expect(coordDisplay(52.7, 4.98)).toBe('52.7000° N, 4.9800° E')
  })

  it('Süd/West über den Betrag', () => {
    expect(coordDisplay(-13.1631, -72.545)).toBe('13.1631° S, 72.5450° W')
  })

  it('0 zählt als Nord/Ost, wie in Python (>= 0)', () => {
    expect(coordDisplay(0, 0)).toBe('0.0000° N, 0.0000° E')
  })

  it('leer ohne Position', () => {
    expect(coordDisplay(null, 4.98)).toBe('')
    expect(coordDisplay(52.7, null)).toBe('')
  })
})

describe('periodDisplay', () => {
  it('der kuratierte Periodenname gewinnt', () => {
    expect(
      periodDisplay({ period_name: '< 4500 BC', period_start: -9600, period_end: null }),
    ).toBe('< 4500 BC')
  })

  it('nur Startjahr → ein Ära-Label', () => {
    expect(periodDisplay({ period_name: null, period_start: -9600, period_end: null })).toBe(
      '9600 BC',
    )
  })

  it('Start und Ende → Spanne mit Gedankenstrich', () => {
    expect(periodDisplay({ period_name: null, period_start: -3000, period_end: -2500 })).toBe(
      '3000 BC – 2500 BC',
    )
  })

  it('positive Jahre sind AD', () => {
    expect(periodDisplay({ period_name: null, period_start: 155, period_end: 500 })).toBe(
      '155 AD – 500 AD',
    )
  })

  it('leer ohne jede Datierung', () => {
    expect(periodDisplay({ period_name: null, period_start: null, period_end: null })).toBe('')
  })
})

describe('longDate (_date_parts()[1], react-ssr Task 14)', () => {
  it('formatiert wie Pythons strftime("%B %d, %Y")', () => {
    expect(longDate('2026-03-14T09:30:00')).toBe('March 14, 2026')
  })

  it('padded den Tag zweistellig — %d, nicht %-d', () => {
    expect(longDate('2026-03-05')).toBe('March 05, 2026')
  })

  it('fällt bei unparsbaren Strings auf value[:10] zurück, wie Python', () => {
    expect(longDate('circa 1400 BC')).toBe('circa 1400')
    expect(longDate('2026-13-01')).toBe('2026-13-01')
  })

  it('leer ohne Wert', () => {
    expect(longDate(null)).toBe('')
    expect(longDate('')).toBe('')
  })
})
