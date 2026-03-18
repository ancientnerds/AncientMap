import { useState } from 'react';
import PipelineHexGraph from '../components/nerv/PipelineHexGraph';

type PipelineTab = 'news' | 'radar' | 'article';

const TABS: { id: PipelineTab; label: string }[] = [
  { id: 'news', label: 'News Pipeline' },
  { id: 'radar', label: 'Radar' },
  { id: 'article', label: 'Article' },
];

export default function LyraOpsPage() {
  const [activeTab, setActiveTab] = useState<PipelineTab>('news');

  return (
    <div className="lyra-ops">
      <style>{`
        .lyra-ops {
          min-height: 100vh;
          background: #000;
          color: var(--nerv-steel);
          font-family: var(--font-ui);
          padding: 24px;
        }
        .lyra-ops-title {
          font-family: var(--font-heading);
          font-size: 14px;
          font-weight: 700;
          color: var(--nerv-o);
          text-transform: uppercase;
          letter-spacing: 2px;
          margin-bottom: 20px;
        }
        .lyra-ops-tabs {
          display: flex;
          gap: 2px;
          margin-bottom: 24px;
        }
        .lyra-ops-tab {
          font-family: var(--font-heading);
          font-size: 10px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          padding: 8px 20px;
          border: 1px solid rgba(0, 204, 102, 0.15);
          background: rgba(0, 204, 102, 0.03);
          color: var(--nerv-steel-dim);
          cursor: pointer;
          transition: all 0.2s;
        }
        .lyra-ops-tab:hover {
          border-color: rgba(0, 204, 102, 0.3);
          color: var(--nerv-steel);
        }
        .lyra-ops-tab.active {
          background: rgba(0, 204, 102, 0.08);
          border-color: var(--nerv-gd);
          color: var(--nerv-g);
          box-shadow: 0 0 8px rgba(0, 204, 102, 0.1);
        }
        .lyra-ops-content {
          max-width: 520px;
        }
      `}</style>

      <div className="lyra-ops-title">
        <span className="led green" style={{ marginRight: 8 }} />
        Lyra Pipeline Operations
      </div>

      <div className="lyra-ops-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`lyra-ops-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="lyra-ops-content">
        <PipelineHexGraph pipeline={activeTab} pollInterval={60000} />
      </div>
    </div>
  );
}
