import { useState, useEffect } from 'react';
import HexNode from './HexNode';
import StepDetailPanel from './StepDetailPanel';
import { LAYOUTS } from './hexLayouts';
import type { HexState } from './hexLayouts';
import type { StepData } from './usePipelineStatus';
import { usePipelineStatus } from './usePipelineStatus';
import './PipelineHexGraph.css';

interface PipelineHexGraphProps {
  pipeline: 'news' | 'radar' | 'article';
  pollInterval?: number;
}

function resolveState(stepData?: StepData): HexState {
  if (!stepData) return 'idle';
  if (stepData.status === 'fail') return 'fail';
  if (stepData.status === 'skip') return 'schd';
  return 'done';
}

const CYCLE_MS = 3600_000; // 1 hour

function formatTimestamp(iso: string | null): string {
  if (!iso) return '\u2014';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  });
}

function useCountdown(lastHeartbeat: string | null): string | null {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (!lastHeartbeat) { setRemaining(null); return; }
    const nextRun = new Date(lastHeartbeat).getTime() + CYCLE_MS;
    const update = () => setRemaining(Math.max(0, nextRun - Date.now()));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [lastHeartbeat]);

  if (remaining == null) return null;
  if (remaining <= 0) return 'imminent';
  const m = Math.floor(remaining / 60_000);
  const s = Math.floor((remaining % 60_000) / 1000);
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

export default function PipelineHexGraph({ pipeline, pollInterval = 60000 }: PipelineHexGraphProps) {
  const layout = LAYOUTS[pipeline];
  const { data, error, loading } = usePipelineStatus(pipeline, pollInterval);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Reset selection on pipeline tab change
  useEffect(() => setSelectedId(null), [pipeline]);

  const steps = data?.steps ?? {};
  const countdown = useCountdown(data?.last_heartbeat ?? null);

  const handleHexClick = (id: string) => {
    setSelectedId(prev => prev === id ? null : id);
  };

  // Find selected node config for the detail panel label/icon
  const selectedNode = selectedId ? layout.nodes.find(n => n.id === selectedId) : null;

  return (
    <div className="phg">
      {/* Status header */}
      <div className="phg-header">
        <span className={`led ${data?.status === 'online' ? 'green' : 'red'}`} />
        <span className="phg-status">
          {loading ? 'Loading...' : data?.status === 'online' ? 'ONLINE' : 'OFFLINE'}
        </span>
        {data?.last_heartbeat && (
          <span className="phg-ts">{formatTimestamp(data.last_heartbeat)}</span>
        )}
        {data?.total_elapsed != null && (
          <span className="phg-elapsed">{data.total_elapsed}s total</span>
        )}
        {error && <span className="phg-error">{error}</span>}
      </div>
      {countdown && (
        <div className="phg-countdown">
          <span className="phg-countdown-label">Next run</span>
          <span className="phg-countdown-value">{countdown}</span>
        </div>
      )}

      {/* Hex hive */}
      <div className="pipeline">
        <div className="measurement-grid" />
        <div className="hive" style={{ maxWidth: layout.hiveWidth, minHeight: layout.hiveHeight }}>
          {/* Source node */}
          <HexNode config={layout.sourceNode} state="src" />

          {/* Pipeline step nodes */}
          {layout.nodes.map((node) => (
            <HexNode
              key={node.id}
              config={node}
              state={resolveState(steps[node.id])}
              stepData={steps[node.id]}
              isSelected={selectedId === node.id}
              onClick={handleHexClick}
            />
          ))}

          {/* Sink nodes */}
          {layout.sinkNodes.map((node) => (
            <HexNode key={node.id} config={node} state="sink" />
          ))}
        </div>
      </div>

      {/* Step detail panel */}
      {selectedNode && (
        <StepDetailPanel
          stepId={selectedId!}
          label={selectedNode.label}
          icon={selectedNode.icon}
          stepData={steps[selectedId!]}
          onClose={() => setSelectedId(null)}
        />
      )}

      {/* Legend */}
      <div className="phg-legend">
        <div className="phg-legend-item">
          <div className="phg-legend-hex" style={{ background: 'var(--nerv-g)' }} />
          Completed
        </div>
        <div className="phg-legend-item">
          <div className="phg-legend-hex" style={{ background: 'rgba(136,136,128,.15)' }} />
          Idle
        </div>
        <div className="phg-legend-item">
          <div className="phg-legend-hex" style={{ background: 'repeating-linear-gradient(-45deg, #000 0px, #000 4px, var(--nerv-o) 4px, var(--nerv-o) 8px)' }} />
          Failed
        </div>
        <div className="phg-legend-item">
          <span style={{ color: 'var(--nerv-steel)' }}>&#9632;</span> LLM
        </div>
        <div className="phg-legend-item">
          <span style={{ color: 'var(--nerv-c)' }}>&#9632;</span> DB
        </div>
      </div>
    </div>
  );
}
