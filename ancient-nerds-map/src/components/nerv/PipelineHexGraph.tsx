import { useState, useEffect, useRef, useCallback } from 'react';
import HexNode from './HexNode';
import StepDetailPanel from './StepDetailPanel';
import { LAYOUTS } from './hexLayouts';
import type { HexState, HexNodeConfig } from './hexLayouts';
import type { StepData } from './usePipelineStatus';
import { usePipelineStatus } from './usePipelineStatus';
import './PipelineHexGraph.css';

interface PipelineHexGraphProps {
  pipeline: 'news' | 'radar' | 'article';
  pollInterval?: number;
}

function resolveState(stepData?: StepData): HexState {
  if (!stepData) return 'idle';
  if (stepData.status === 'run') return 'run';
  if (stepData.status === 'fail') return 'fail';
  if (stepData.status === 'skip') return 'schd';
  return 'done';
}

function deriveSourceState(steps: Record<string, StepData>): HexState {
  return Object.keys(steps).length === 0 ? 'idle' : 'done';
}

function deriveSinkState(steps: Record<string, StepData>): HexState {
  const vals = Object.values(steps);
  if (vals.length === 0) return 'idle';
  if (vals.some(s => s.status === 'run')) return 'idle';
  if (vals.some(s => s.status === 'fail')) return 'fail';
  return 'done';
}

const CYCLE_MS = 3600_000;

function formatTimestamp(iso: string | null): string {
  if (!iso) return '\u2014';
  const d = new Date(iso);
  return d.toLocaleString('en-GB', {
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

// -- Replay hook --
// Replays the last cycle step-by-step using real elapsed times, scaled to fit ~8s total.
interface ReplayState {
  /** Index into layout.nodes — steps 0..i-1 are "done", step i is "run", rest idle. -1 = source phase, nodes.length = sinks phase */
  step: number;
  active: boolean;
}

function useReplay(nodes: HexNodeConfig[], steps: Record<string, StepData>) {
  const [replay, setReplay] = useState<ReplayState>({ step: -1, active: false });
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const stop = useCallback(() => {
    clearTimeout(timerRef.current);
    setReplay({ step: -1, active: false });
  }, []);

  const start = useCallback(() => {
    // Collect elapsed times for each node that has step data
    const timings = nodes.map(n => {
      const sd = steps[n.id];
      return sd ? sd.elapsed : 0;
    });
    const totalReal = timings.reduce((a, b) => a + b, 0) || 1;
    const TARGET_DURATION = 8; // seconds for full replay
    const MIN_STEP_MS = 400; // minimum visible time per step
    const scale = TARGET_DURATION / totalReal;

    setReplay({ step: -1, active: true }); // source lights up

    let idx = 0;
    const advance = () => {
      if (idx > nodes.length) { // past sinks — done
        stop();
        return;
      }
      setReplay({ step: idx, active: true });
      const ms = idx < nodes.length
        ? Math.max(MIN_STEP_MS, timings[idx] * scale * 1000)
        : 600; // sink display time
      idx++;
      timerRef.current = setTimeout(advance, ms);
    };

    // Start after a brief source pause
    timerRef.current = setTimeout(advance, 500);
  }, [nodes, steps, stop]);

  // Cleanup on unmount
  useEffect(() => () => clearTimeout(timerRef.current), []);

  return { replay, start, stop };
}

export default function PipelineHexGraph({ pipeline, pollInterval = 60000 }: PipelineHexGraphProps) {
  const layout = LAYOUTS[pipeline];
  const { data, error, loading } = usePipelineStatus(pipeline, pollInterval);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Reset selection on pipeline tab change
  useEffect(() => setSelectedId(null), [pipeline]);

  const steps = data?.steps ?? {};
  const countdown = useCountdown(data?.last_heartbeat ?? null);
  const { replay, start: startReplay, stop: stopReplay } = useReplay(layout.nodes, steps);

  // Stop replay on tab change
  useEffect(() => stopReplay(), [pipeline, stopReplay]);

  const hasStepData = Object.keys(steps).length > 0;

  // Resolve hex states — during replay, override with replay state
  const getNodeState = (node: HexNodeConfig, idx: number): HexState => {
    if (!replay.active) return resolveState(steps[node.id]);
    if (idx < replay.step) {
      // Already replayed — show actual final state
      const sd = steps[node.id];
      return sd?.status === 'fail' ? 'fail' : sd?.status === 'skip' ? 'schd' : 'done';
    }
    if (idx === replay.step) return 'run';
    return 'idle';
  };

  const getSourceState = (): HexState => {
    if (replay.active) return replay.step >= 0 ? 'done' : 'run';
    return deriveSourceState(steps) === 'idle' ? 'src' : 'done';
  };

  const getSinkState = (): HexState => {
    if (replay.active) return replay.step > layout.nodes.length - 1 ? 'done' : 'idle';
    const s = deriveSinkState(steps);
    return s === 'idle' ? 'sink' : s;
  };

  const handleHexClick = (id: string) => {
    if (replay.active) return; // ignore clicks during replay
    setSelectedId(prev => prev === id ? null : id);
  };

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
        {hasStepData && !replay.active && (
          <button className="phg-replay-btn" onClick={startReplay} title="Replay last cycle">
            &#9654;
          </button>
        )}
        {replay.active && (
          <button className="phg-replay-btn replaying" onClick={stopReplay} title="Stop replay">
            &#9632;
          </button>
        )}
        {error && <span className="phg-error">{error}</span>}
      </div>
      {countdown && !replay.active && (
        <div className="phg-countdown">
          <span className="phg-countdown-label">Next run</span>
          <span className="phg-countdown-value">{countdown}</span>
        </div>
      )}
      {replay.active && (
        <div className="phg-countdown">
          <span className="phg-countdown-label">Replaying</span>
          <span className="phg-countdown-value" style={{ color: 'var(--nerv-g)' }}>
            {replay.step < 0 ? 'Source' : replay.step < layout.nodes.length ? layout.nodes[replay.step].label : 'Output'}
          </span>
        </div>
      )}

      {/* Hex hive */}
      <div className="pipeline">
        <div className="measurement-grid" />
        <div className="hive" style={{ maxWidth: layout.hiveWidth, minHeight: layout.hiveHeight }}>
          {/* Source node */}
          <HexNode config={layout.sourceNode} state={getSourceState()} />

          {/* Pipeline step nodes */}
          {layout.nodes.map((node, idx) => (
            <HexNode
              key={node.id}
              config={node}
              state={getNodeState(node, idx)}
              stepData={replay.active ? undefined : steps[node.id]}
              isSelected={!replay.active && selectedId === node.id}
              onClick={replay.active ? undefined : handleHexClick}
            />
          ))}

          {/* Sink nodes */}
          {layout.sinkNodes.map((node) => (
            <HexNode key={node.id} config={node} state={getSinkState()} />
          ))}
        </div>
      </div>

      {/* Step detail panel */}
      {selectedNode && !replay.active && (
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
