/**
 * PaperCard — one research paper as a hero card.
 *
 * Extracted from the inline markup of TheoPage's public research library
 * (2026-09-10) when the homepage's papers section asked for the same look:
 * "Why is the research paper gallery so boring? Why doesn't it look like
 * Theo's research tasks, where you get cards with images?" One definition,
 * two callers — the card cannot look like two different things.
 *
 * The wrapper is an <a> when the card has an href (the homepage links
 * /research/{slug} and wants a crawlable link) and the role="button" <div>
 * TheoPage always used otherwise, because that page navigates in JS to
 * /research.html?slug=… . The footer is the caller's: TheoPage prints the
 * author avatar, the quality badge, the age and a share button, the homepage
 * one plain line of numbers.
 */
import type { ReactNode } from 'react'

import { track } from '../../analytics'

import '../../styles/paper-card.css'

export interface PaperCardPaper {
  title: string
  /** Hero banner. Null/'' for a paper without one — then the box is the vignette alone. */
  cover: string | null
  /** The card blurb (card_description). Null/'' when the paper has none. */
  description: string | null
}

/** Exactly one of href / onOpen: a card is either a link or a scripted button. */
type PaperCardProps = {
  paper: PaperCardPaper
  /** Content of .theo-public-card-footer. */
  footer: ReactNode
  /** Extra wrapper class, e.g. theo-public-card--own. */
  className?: string
} & ({ href: string; onOpen?: never } | { href?: never; onOpen: () => void })

export default function PaperCard(props: PaperCardProps) {
  const { paper, footer, className } = props
  const cls = className ? `theo-public-card ${className}` : 'theo-public-card'
  const inner = (
    <>
      <div className="theo-public-card-hero">
        {paper.cover && (
          <img src={paper.cover} alt={paper.title} className="theo-public-card-img" loading="lazy" />
        )}
        <div className="theo-public-card-vignette" />
        <div className="theo-public-card-title">{paper.title}</div>
      </div>
      <div className="theo-public-card-body">
        {paper.description && <p className="theo-public-card-desc">{paper.description}</p>}
        <div className="theo-public-card-footer">{footer}</div>
      </div>
    </>
  )
  if (props.href !== undefined) {
    return (
      <a className={cls} href={props.href} onClick={() => track('paper_open', { paper: props.href, method: 'page' })}>
        {inner}
      </a>
    )
  }
  const open = () => {
    track('paper_open', { paper: paper.title, method: 'overlay' })
    props.onOpen()
  }
  return (
    <div
      className={cls}
      role="button"
      tabIndex={0}
      aria-label={paper.title}
      onClick={open}
      onKeyDown={e => {
        if (e.key === 'Enter') open()
      }}
    >
      {inner}
    </div>
  )
}
