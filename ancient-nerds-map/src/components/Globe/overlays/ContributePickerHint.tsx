/**
 * ContributePickerHint - Shows instruction when contribute map picker is active
 * Displays below coordinates with back button
 */

interface ContributePickerHintProps {
  active: boolean
  onCancel?: () => void
}

export function ContributePickerHint({ active, onCancel }: ContributePickerHintProps) {
  if (!active) return null

  return (
    <div className="contribute-picker-hint">
      <button className="picker-back-btn" onClick={onCancel} title="Back to form">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <span>Click on globe to set location</span>
    </div>
  )
}
