import { CATEGORY_COLORS, PERIOD_COLORS } from '../../../data/sites'
import type { AdminEditPanelProps } from '../types'

export function AdminEditPanel({
  editedSite,
  onEditedSiteChange,
  saveError,
  isSaving,
  onSave,
  onCancel
}: AdminEditPanelProps) {
  return (
    <div className="popup-admin-edit">
      <div className="admin-edit-field">
        <label>Name</label>
        <input
          type="text"
          value={editedSite.title}
          onChange={(e) => onEditedSiteChange({ ...editedSite, title: e.target.value })}
        />
      </div>
      <div className="admin-edit-field">
        <label>Description</label>
        <textarea
          value={editedSite.description || ''}
          onChange={(e) => onEditedSiteChange({ ...editedSite, description: e.target.value })}
          rows={4}
        />
      </div>
      <div className="admin-edit-field">
        <label>Location</label>
        <input
          type="text"
          value={editedSite.location || ''}
          onChange={(e) => onEditedSiteChange({ ...editedSite, location: e.target.value })}
        />
      </div>
      <div className="admin-edit-row">
        <div className="admin-edit-field">
          <label>Latitude</label>
          <input
            type="number"
            step="0.0001"
            value={editedSite.coordinates[1]}
            onChange={(e) => onEditedSiteChange({
              ...editedSite,
              coordinates: [editedSite.coordinates[0], parseFloat(e.target.value) || 0]
            })}
          />
        </div>
        <div className="admin-edit-field">
          <label>Longitude</label>
          <input
            type="number"
            step="0.0001"
            value={editedSite.coordinates[0]}
            onChange={(e) => onEditedSiteChange({
              ...editedSite,
              coordinates: [parseFloat(e.target.value) || 0, editedSite.coordinates[1]]
            })}
          />
        </div>
      </div>
      <div className="admin-edit-row">
        <div className="admin-edit-field">
          <label>Category</label>
          <select
            value={editedSite.category}
            onChange={(e) => onEditedSiteChange({ ...editedSite, category: e.target.value as typeof editedSite.category })}
          >
            {Object.keys(CATEGORY_COLORS).map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
        <div className="admin-edit-field">
          <label>Period</label>
          <select
            value={editedSite.period}
            onChange={(e) => onEditedSiteChange({ ...editedSite, period: e.target.value as typeof editedSite.period })}
          >
            {Object.keys(PERIOD_COLORS).map(period => (
              <option key={period} value={period}>{period}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="admin-edit-field">
        <label>Source URL</label>
        <input
          type="url"
          value={editedSite.sourceUrl || ''}
          onChange={(e) => onEditedSiteChange({ ...editedSite, sourceUrl: e.target.value })}
          placeholder="https://..."
        />
      </div>
      {saveError && <div className="admin-edit-error">{saveError}</div>}
      <div className="admin-edit-actions">
        <button className="admin-btn cancel" onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
        <button className="admin-btn save" onClick={onSave} disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  )
}
