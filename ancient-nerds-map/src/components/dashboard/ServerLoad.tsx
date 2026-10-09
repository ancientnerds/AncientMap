import { fmtDay, fmtInt, fmtStamp } from './format'
import { LineChart } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { LoadLevel, ServerData, ServerReport } from './types'
import type { Loaded } from './useStats'

const LEVEL_CLASS: Record<LoadLevel, string> = {
  ok: 'dash-delta--up',
  warn: 'dash-vital--ni',
  bad: 'dash-delta--down',
}

function pct(v: number | null): string {
  return v === null ? '–' : `${Math.round(v)} %`
}

/** The lines the Attention panel adds: a resource past its amber limit, and a
 *  sampler that went quiet. A quiet sampler is amber, not red: the server
 *  may be fine, but nobody is watching it. */
export function serverAttention(r: ServerReport | null): Array<{ key: string; text: string; tone: LoadLevel }> {
  if (!r) return []
  const lines: Array<{ key: string; text: string; tone: LoadLevel }> = []
  if (r.silent) {
    lines.push({
      key: 'server:silent',
      text: 'Server: no load sample for 20 minutes - the sampler in Lyra is not running.',
      tone: 'warn',
    })
  }
  const today = r.days[r.days.length - 1]
  if (r.levels.disk !== 'ok' && r.now) {
    lines.push({
      key: 'server:disk',
      text: `Server disk ${pct(r.now.disk_used)} full, ${r.now.disk_free_gb ?? '–'} GB left.`,
      tone: r.levels.disk,
    })
  }
  if (r.levels.memory !== 'ok' && today) {
    lines.push({ key: 'server:memory', text: `Server memory peaked at ${pct(today.mem_peak)} today - there is no swap.`, tone: r.levels.memory })
  }
  if (r.levels.cpu !== 'ok' && today) {
    lines.push({ key: 'server:cpu', text: `Server CPU peaked at ${pct(today.cpu_peak)} today.`, tone: r.levels.cpu })
  }
  return lines
}

/**
 * Is the server keeping up — the host's CPU, memory and disk now and per day
 * since the samples began, with the day's visitors beside them, so a growing
 * audience and a growing load can be read against each other.
 */
export function ServerLoad({ state }: { state: Loaded<ServerData> }) {
  const d = state.data
  const r = d?.report
  const now = r?.now
  const days = r?.days ?? []
  const today = days[days.length - 1]
  return (
    <Panel question="Is the server keeping up?" wide>
      <Status state={state} />
      {d && !r && <p className="dash-status">{d.log_reason}</p>}
      {r && now && (
        <>
          <div className="dash-tiles">
            <Tile
              label="CPU, last 5 min"
              value={pct(now.cpu)}
              sub={`of ${now.cores ?? '?'} cores · peak today ${pct(today?.cpu_peak ?? null)}`}
              subCls={LEVEL_CLASS[r.levels.cpu]}
            />
            <Tile
              label="Memory in use"
              value={pct(now.mem_used)}
              sub={`of ${now.mem_total_mb ? `${Math.round(now.mem_total_mb / 1024)} GB` : '?'} · peak today ${pct(today?.mem_peak ?? null)}`}
              subCls={LEVEL_CLASS[r.levels.memory]}
            />
            <Tile
              label="Disk used"
              value={pct(now.disk_used)}
              sub={`${now.disk_free_gb ?? '–'} GB free`}
              subCls={LEVEL_CLASS[r.levels.disk]}
            />
            <Tile label="Load, 5 min" value={now.load5.toFixed(2)} sub={`${now.cores ?? '?'} cores = full`} />
          </div>
          {r.silent && (
            <p className="dash-status dash-status--error">
              No sample since {fmtStamp(now.t)} UTC - the sampler in Lyra is not running.
            </p>
          )}
          {days.length >= 2 && (
            <>
              <LineChart
                series={[
                  { label: 'CPU, busiest minutes', values: days.map(x => x.cpu_peak), className: 'dash-line-human' },
                  { label: 'memory peak', values: days.map(x => x.mem_peak), className: 'dash-line-all' },
                  { label: 'disk used', values: days.map(x => x.disk_used), className: 'dash-line-ink' },
                ]}
                titles={days.map(
                  x =>
                    `${fmtDay(x.day)}: CPU ${pct(x.cpu_avg)} on average, ${pct(x.cpu_peak)} at peak · memory ${pct(x.mem_peak)} · disk ${pct(x.disk_used)}`
                )}
                axis={[fmtDay(days[0].day), 'Percent per day, 0-100', fmtDay(days[days.length - 1].day)]}
                label={`Server load per day from ${fmtDay(days[0].day)}`}
                max={100}
              />
              <LineChart
                small
                series={[{ label: 'visitors', values: days.map(x => x.visitors), className: 'dash-line-all' }]}
                titles={days.map(x => `${fmtDay(x.day)}: ${x.visitors === null ? 'no count' : `${fmtInt(x.visitors)} visitors`}`)}
                axis={[fmtDay(days[0].day), 'Visitors per day, for comparison', fmtDay(days[days.length - 1].day)]}
                label="Visitors per day over the same days"
              />
            </>
          )}
        </>
      )}
      <HowCounted>
        Lyra reads the host every five minutes: the share of all cores busy since the last reading, the load average,
        the memory the kernel could not hand out without swapping (this server has no swap, so that is the limit that
        stops processes), and the root disk, which the images, the database and Docker's volumes share. The days
        before the sampler come from the server's own sysstat records, ten-minute readings without disk. Amber from{' '}
        {r ? `${r.limits.disk[0]} % disk, ${r.limits.memory[0]} % memory, ${r.limits.cpu[0]} % CPU` : 'the first limit'},
        red from{' '}
        {r ? `${r.limits.disk[1]} %, ${r.limits.memory[1]} % and ${r.limits.cpu[1]} %` : 'the second'}; the warnings
        also stand in "What needs attention?". The visitors are not what loads the server - the API answers them at a
        fraction of one core; Lyra, Theo, image runs and deploys are.
      </HowCounted>
    </Panel>
  )
}
