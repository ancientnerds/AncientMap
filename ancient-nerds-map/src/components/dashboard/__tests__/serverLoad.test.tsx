/** The server panel and the Attention lines it adds, with the shapes /api/stats/server answers. */
import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { attentionLines } from '../Attention'
import { ServerLoad, serverAttention } from '../ServerLoad'
import type { ServerData, ServerReport } from '../types'

const text = (html: string) => html.replace(/<!-- -->/g, '')
const ok = <T,>(data: T) => ({ data, error: null })

const REPORT: ServerReport = {
  now: {
    t: '2026-10-10T08:05:00+00:00',
    cpu: 3.1,
    load5: 0.3,
    mem_used: 31.2,
    mem_total_mb: 11960,
    cores: 6,
    disk_used: 59.1,
    disk_free_gb: 79.8,
  },
  days: [
    { day: '2026-10-08', cpu_avg: 2.6, cpu_peak: 17.6, load_peak: 0.8, mem_peak: 36, disk_used: null, visitors: 173 },
    { day: '2026-10-09', cpu_avg: 4.3, cpu_peak: 36.5, load_peak: 2.2, mem_peak: 37, disk_used: 59.1, visitors: 195 },
  ],
  levels: { disk: 'ok', memory: 'ok', cpu: 'ok' },
  silent: false,
  limits: { disk: [80, 90], memory: [85, 95], cpu: [80, 95] },
}

describe('serverAttention', () => {
  it('says nothing while every level is ok', () => {
    expect(serverAttention(REPORT)).toEqual([])
    expect(serverAttention(null)).toEqual([])
  })

  it('names a filling disk with the space left, in its level', () => {
    const full = { ...REPORT, levels: { ...REPORT.levels, disk: 'bad' as const }, now: { ...REPORT.now!, disk_used: 91.4, disk_free_gb: 17.2 } }
    expect(serverAttention(full)).toEqual([{ key: 'server:disk', text: 'Server disk 91 % full, 17.2 GB left.', tone: 'bad' }])
  })

  it('warns when the sampler went quiet', () => {
    expect(serverAttention({ ...REPORT, silent: true })[0].key).toBe('server:silent')
  })

  it('leads the Attention panel', () => {
    const memory = { ...REPORT, levels: { ...REPORT.levels, memory: 'warn' as const } }
    const lines = attentionLines(null, null, null, null, null, { report: memory, log_reason: null })
    expect(lines[0]).toEqual({ key: 'server:memory', text: 'Server memory peaked at 37 % today - there is no swap.', tone: 'warn' })
  })
})

describe('ServerLoad', () => {
  it('shows the four tiles, the load lines and the visitors beside them', () => {
    const html = text(renderToString(<ServerLoad state={ok<ServerData>({ report: REPORT, log_reason: null })} />))
    expect(html).toContain('Is the server keeping up?')
    expect(html).toContain('3 %')
    expect(html).toContain('of 6 cores · peak today 37 %')
    expect(html).toContain('79.8 GB free')
    expect(html).toContain('dash-line-ink')
    expect(html).toContain('Visitors per day, for comparison')
  })

  it('says when the sampler is silent', () => {
    const html = text(renderToString(<ServerLoad state={ok<ServerData>({ report: { ...REPORT, silent: true }, log_reason: null })} />))
    expect(html).toContain('No sample since 10 Oct 08:05 UTC')
  })

  it('names the missing log on a development box', () => {
    const html = renderToString(<ServerLoad state={ok<ServerData>({ report: null, log_reason: 'no server_load.jsonl here' })} />)
    expect(html).toContain('no server_load.jsonl here')
  })
})
