interface SectionHeadProps {
  fig: number
  name: string
  status: string
}

/** `>_ [ fig. N — name ]` — the section label of the live homepage blocks. */
export default function SectionHead({ fig, name, status }: SectionHeadProps) {
  return (
    <div className="ll-head">
      <h2 className="ll-fig">
        &gt;_ [ fig. {fig} — <b>{name}</b> ]
      </h2>
      <span className="ll-status">{status}</span>
    </div>
  )
}
