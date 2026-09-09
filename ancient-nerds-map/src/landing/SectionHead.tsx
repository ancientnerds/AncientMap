interface SectionHeadProps {
  fig: number
  name: string
  status: string
}

/**
 * `>_ [ fig. N — name ]` — the section label of the live homepage blocks.
 *
 * The `ll-fig-N` id is the accessible name of the surrounding <section>,
 * which points at it with aria-labelledby: a landmark without a name is
 * one more unlabelled "region" in a screen reader's landmark list. The
 * decoration around the name is aria-hidden, so that name is "stories,
 * live" and not "greater than sign underscore left bracket fig. 1 …".
 */
export default function SectionHead({ fig, name, status }: SectionHeadProps) {
  return (
    <div className="ll-head">
      <h2 className="ll-fig" id={`ll-fig-${fig}`}>
        <span aria-hidden="true">{`>_ [ fig. ${fig} — `}</span>
        <b>{name}</b>
        <span aria-hidden="true">{' ]'}</span>
      </h2>
      <span className="ll-status">{status}</span>
    </div>
  )
}
