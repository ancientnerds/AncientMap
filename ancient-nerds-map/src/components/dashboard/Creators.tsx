import { BarList, type BarItem } from './BarList'
import { fmtDay, fmtInt, fmtStamp } from './format'
import { AxisChart, niceMax } from './Lines'
import { HowCounted, Panel, Status } from './Panel'
import { Tile } from './Tile'
import type { CreatorChannel, CreatorsData } from './types'
import type { Loaded } from './useStats'

export function channelItem(c: CreatorChannel): BarItem {
  return {
    key: `ch:${c.channel}`,
    label: c.channel,
    value: c.starts + c.clicks,
    hint: `${fmtInt(c.starts)} started here · ${fmtInt(c.clicks)} to YouTube`,
  }
}

/**
 * How much do we send to the creators - the 39 channels Lyra reads get an
 * audience on our story pages: who starts their video in place, and who
 * follows a link to it on YouTube. Owner, 2026-10-09: traffic for the
 * creators is good for them, and creators who see it may use the platform.
 */
export function Creators({ state }: { state: Loaded<CreatorsData> }) {
  const d = state.data
  return (
    <Panel question="How much do we send to the creators?" wide>
      <Status state={state} />
      {d && (
        <>
          <div className="dash-tiles">
            <Tile label="Videos started" value={d.totals.starts} sub={`${fmtInt(d.totals.videos)} videos, on our story pages`} />
            <Tile label="Clicks to YouTube" value={d.totals.clicks} sub={`since ${fmtStamp(d.clicks_since)} UTC`} />
            <Tile label="Channels reached" value={d.totals.channels} sub="of the channels Lyra reads" />
            <Tile label="Viewers" value={d.totals.viewers} sub="sessions per video and day" />
          </div>
          {d.days.length >= 2 && (
            <AxisChart
              small
              left={{ max: niceMax(Math.max(...d.days.map(x => x.starts + x.clicks), 1)), format: v => fmtInt(Math.round(v)) }}
              bars={[
                { label: 'started on our pages', values: d.days.map(x => x.starts), className: 'dash-bar-human' },
                { label: 'clicked to YouTube', values: d.days.map(x => x.clicks), className: 'dash-bar-red' },
              ]}
              titles={d.days.map(x => `${fmtDay(x.day)}: ${fmtInt(x.starts)} started, ${fmtInt(x.clicks)} to YouTube`)}
              axis={[fmtDay(d.days[0].day), 'Per day', fmtDay(d.days[d.days.length - 1].day)]}
              label="Creator videos started and clicked per day"
            />
          )}
          <div className="dash-lists">
            <div>
              <h3>Channels</h3>
              <BarList items={d.channels.map(channelItem)} empty="No creator video started so far." />
            </div>
            <div>
              <h3>Most started videos</h3>
              <BarList
                items={d.videos.map(
                  (v): BarItem => ({ key: `v:${v.id}`, label: v.title, value: v.starts, hint: v.channel, href: `https://www.youtube.com/watch?v=${v.id}`, wrap: true })
                )}
                empty="No creator video started so far."
              />
            </div>
          </div>
        </>
      )}
      <HowCounted>
        A start is a click on the video in a story, which plays it in place from youtube-nocookie.com; a click to
        YouTube is a link out to a video there, counted from the deploy that stopped a poster click from also counting
        as one (before it, 77 of 83 such clicks were plays). From 10 October a click names its video, so it is
        credited to the channel; the clicks between are listed as "not attributed". How long a video is watched is
        not measured yet - the player would have to report it.
      </HowCounted>
    </Panel>
  )
}
