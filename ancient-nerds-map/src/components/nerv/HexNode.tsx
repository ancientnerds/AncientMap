import { useState, useEffect, useRef } from 'react';
import type { HexNodeConfig, HexState } from './hexLayouts';
import type { StepData } from './usePipelineStatus';

interface HexNodeProps {
  config: HexNodeConfig;
  state: HexState;
  stepData?: StepData;
  isSelected?: boolean;
  onClick?: (id: string) => void;
}

function formatMeta(stepData?: StepData): string {
  if (!stepData) return '';
  if (stepData.status === 'skip') return 'skipped';
  if (stepData.status === 'fail') return `ERR ${stepData.elapsed}s`;
  return `${stepData.count} ${stepData.elapsed}s`;
}

/** Live stopwatch that ticks every 100ms while the hex is in 'run' state */
function useRunTimer(isRunning: boolean): string | null {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(0);

  useEffect(() => {
    if (!isRunning) { setElapsed(0); return; }
    startRef.current = performance.now();
    const tick = () => setElapsed((performance.now() - startRef.current) / 1000);
    const id = setInterval(tick, 100);
    return () => clearInterval(id);
  }, [isRunning]);

  if (!isRunning) return null;
  return `${elapsed.toFixed(1)}s`;
}

/** SVG hex polygon for the animated dash border on "run" state */
const DashOverlay = () => (
  <div className="hx-dash">
    <svg viewBox="0 0 110 128">
      <polygon points="55,1 109,33 109,95 55,127 1,95 1,33" />
    </svg>
  </div>
);

export default function HexNode({ config, state, stepData, isSelected, onClick }: HexNodeProps) {
  const meta = formatMeta(stepData);
  const runTimer = useRunTimer(state === 'run');
  const cls = `hx ${state}${isSelected ? ' selected' : ''}`;

  return (
    <div
      className={cls}
      data-type={config.dataType}
      style={{ left: config.position.left, top: config.position.top }}
      onClick={onClick ? () => onClick(config.id) : undefined}
    >
      <div className="hx-brd" />
      {state === 'run' && <DashOverlay />}
      <div className="hx-fill">
        <div className="hx-ico-row">
          <div className="hx-ico">{config.icon}</div>
          {config.ragPhase && <div className={`hx-rag hx-rag-${config.ragPhase}`}>{config.ragPhase}</div>}
        </div>
        <div className="hx-nm">{config.label}</div>
        {runTimer
          ? <div className="hx-meta hx-meta-run">{runTimer}</div>
          : meta
            ? <div className="hx-meta">{meta}</div>
            : null
        }
        <div className="hx-step">{config.stepNumber}</div>
      </div>
    </div>
  );
}
