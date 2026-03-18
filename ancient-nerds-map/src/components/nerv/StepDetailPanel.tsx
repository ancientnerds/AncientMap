import { useState, useCallback } from 'react';
import type { StepData } from './usePipelineStatus';
import './StepDetailPanel.css';

interface StepDetailPanelProps {
  stepId: string;
  label: string;
  icon: string;
  stepData?: StepData;
  onClose: () => void;
}

const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  done: { text: 'DONE', cls: 'sdp-badge-done' },
  fail: { text: 'FAIL', cls: 'sdp-badge-fail' },
  skip: { text: 'SKIP', cls: 'sdp-badge-skip' },
};

const ADMIN_KEY_STORAGE = 'lyra_admin_key';

export default function StepDetailPanel({ stepId, label, icon, stepData, onClose }: StepDetailPanelProps) {
  const [logs, setLogs] = useState<string | null>(null);
  const [logLoading, setLogLoading] = useState(false);
  const [logError, setLogError] = useState<string | null>(null);
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [keyValue, setKeyValue] = useState('');

  const status = stepData ? STATUS_LABELS[stepData.status] ?? STATUS_LABELS.done : null;

  const fetchLogs = useCallback(async (key: string) => {
    setLogLoading(true);
    setLogError(null);
    try {
      const res = await fetch(`/api/news/logs?search=${encodeURIComponent(stepId)}&lines=50&key=${encodeURIComponent(key)}`);
      if (res.status === 403) {
        sessionStorage.removeItem(ADMIN_KEY_STORAGE);
        setLogError('Invalid admin key');
        setShowKeyInput(true);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      setLogs(text || '(no matching log lines)');
    } catch (err) {
      setLogError(err instanceof Error ? err.message : 'Failed to fetch logs');
    } finally {
      setLogLoading(false);
    }
  }, [stepId]);

  const handleViewLogs = () => {
    const stored = sessionStorage.getItem(ADMIN_KEY_STORAGE);
    if (stored) {
      fetchLogs(stored);
    } else {
      setShowKeyInput(true);
    }
  };

  const handleKeySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyValue.trim()) return;
    sessionStorage.setItem(ADMIN_KEY_STORAGE, keyValue.trim());
    setShowKeyInput(false);
    fetchLogs(keyValue.trim());
  };

  return (
    <div className="sdp">
      <button className="sdp-close" onClick={onClose} aria-label="Close">&times;</button>

      {/* Header */}
      <div className="sdp-header">
        <span className="sdp-icon">{icon}</span>
        <span className="sdp-label">{label}</span>
        {status && <span className={`sdp-badge ${status.cls}`}>{status.text}</span>}
      </div>

      {/* Stats */}
      {stepData && stepData.status !== 'skip' && (
        <div className="sdp-stats">
          <span>Processed: <strong>{stepData.count >= 0 ? stepData.count : '\u2014'}</strong></span>
          <span>Elapsed: <strong>{stepData.elapsed}s</strong></span>
        </div>
      )}

      {/* Error */}
      {stepData?.error && (
        <div className="sdp-error">
          <div className="sdp-error-title">Error</div>
          <pre className="sdp-error-text">{stepData.error}</pre>
        </div>
      )}

      {/* Log viewer */}
      <div className="sdp-logs">
        {logs == null && !showKeyInput && (
          <button className="sdp-logs-btn" onClick={handleViewLogs} disabled={logLoading}>
            {logLoading ? 'Loading...' : 'View Logs'}
          </button>
        )}

        {showKeyInput && (
          <form className="sdp-key-form" onSubmit={handleKeySubmit}>
            <input
              className="sdp-key-input"
              type="password"
              placeholder="Admin key"
              value={keyValue}
              onChange={e => setKeyValue(e.target.value)}
              autoFocus
            />
            <button className="sdp-key-submit" type="submit">Go</button>
          </form>
        )}

        {logError && <div className="sdp-log-error">{logError}</div>}

        {logs != null && (
          <pre className="sdp-log-output">{logs}</pre>
        )}
      </div>
    </div>
  );
}
