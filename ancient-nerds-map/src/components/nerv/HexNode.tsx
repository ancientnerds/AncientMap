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

export default function HexNode({ config, state, stepData, isSelected, onClick }: HexNodeProps) {
  const meta = formatMeta(stepData);
  const cls = `hx ${state}${isSelected ? ' selected' : ''}`;

  return (
    <div
      className={cls}
      data-type={config.dataType}
      style={{ left: config.position.left, top: config.position.top }}
      onClick={onClick ? () => onClick(config.id) : undefined}
    >
      <div className="hx-brd" />
      <div className="hx-fill">
        <div className="hx-ico">{config.icon}</div>
        <div className="hx-nm">{config.label}</div>
        {meta && <div className="hx-meta">{meta}</div>}
        <div className="hx-step">{config.stepNumber}</div>
      </div>
    </div>
  );
}
