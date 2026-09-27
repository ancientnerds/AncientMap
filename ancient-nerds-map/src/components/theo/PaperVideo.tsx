/**
 * PaperVideo — a YouTube video made from the paper, as a click-to-play figure.
 *
 * Same player as the story page (InlineVideo, the StoryArticle figure): the
 * server renders a real link to YouTube, the iframe mounts only after a
 * click, so no request reaches YouTube before the visitor asks for it. The
 * poster is our own studio thumbnail from our server (owner decision #13,
 * spec §2.7), loaded lazily so it never competes with the hero image; the
 * .story-video img rule (story-page.css) reserves its 16:9 frame, so its late
 * arrival moves no #ev-NN target (useEvidenceHashScroll does not wait for lazy
 * images). A video registered without one keeps the framed posterless variant
 * (.is-posterless) with the play glyph.
 */

import InlineVideo from '../news/InlineVideo'
import { longDate } from '../../seo/display'
import type { ResearchVideo } from '../../types/anRoute'
import { youtubeWatchUrl } from './paperExtras'

import '../../styles/story-page.css'

export default function PaperVideo({ video }: { video: ResearchVideo }) {
  const watchUrl = youtubeWatchUrl(video.youtube_id)
  return (
    <figure className="story-video theo-paper-video">
      <InlineVideo
        videoId={video.youtube_id}
        title={video.title}
        watchUrl={watchUrl}
        embedClassName="story-video-embed"
      >
        {play => (
          // A real link: right-, middle- and ctrl-click keep working, a plain
          // click plays the video here.
          <a
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={`story-video-link${video.poster ? '' : ' is-posterless'}`}
            onClick={e => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              play()
            }}
          >
            {video.poster && <img src={video.poster} alt="" loading="lazy" />}
            <span className="story-play" aria-hidden="true">▶</span>
          </a>
        )}
      </InlineVideo>
      <figcaption>
        {'Video: '}
        <a href={watchUrl} target="_blank" rel="noopener noreferrer">
          {video.title}
        </a>
        {` · ${longDate(video.published_at)}`}
      </figcaption>
    </figure>
  )
}
