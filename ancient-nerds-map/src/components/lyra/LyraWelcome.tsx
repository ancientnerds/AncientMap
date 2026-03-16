import type { LyraContextType } from '../../types/ai'

interface LyraWelcomeProps {
  mode: 'modal' | 'page'
  contextType: LyraContextType
  onPromptClick: (question: string) => void
  disabled: boolean
}

const CAPABILITIES = [
  { icon: '\uD83D\uDD0D', label: 'Site Search', desc: 'Search 40K+ archaeological sites', prompt: 'Find megalithic temples in Malta' },
  { icon: '\uD83D\uDCE1', label: 'News Radar', desc: 'Recent discoveries from YouTube', prompt: "What has Lyra discovered on her radar this week?" },
  { icon: '\uD83D\uDC51', label: 'Empire Intelligence', desc: '46 civilizations with warfare & economy data', prompt: 'Compare the military tech of Rome and the Mongol Empire' },
  { icon: '\uD83D\uDCF7', label: 'Visual Research', desc: 'Photos, transcripts, and deep-dive articles', prompt: 'Show me photos of Pompeii' },
]

interface PromptCategory {
  label: string
  prompts: string[]
}

const CURATED_PROMPTS: Record<LyraContextType, PromptCategory[]> = {
  global: [
    { label: 'Explore Sites', prompts: ['Find underwater ruins in the Mediterranean', 'What are the oldest known cities in the world?'] },
    { label: 'Recent Discoveries', prompts: ["What has Lyra discovered on her radar this week?", 'Are there any theories about polygonal masonry being cast rather than carved?'] },
    { label: 'Empires & Wars', prompts: ['Compare the military tech of Rome and the Mongol Empire', 'What was the economy of the Aztec Empire like?'] },
    { label: 'Deep Dives', prompts: ['Show me photos of Pompeii', 'What channels does Lyra monitor?'] },
  ],
  site: [
    { label: 'About This Site', prompts: ['What are all the names this site goes by?', 'Show me images of this site'] },
    { label: 'Explore Nearby', prompts: ['What other sites are nearby?', 'Any recent YouTube coverage of this site?'] },
  ],
  empire: [
    { label: 'Military & Economy', prompts: ['What weapons and fortifications did they use?', 'What was their economy like — trade, coinage, roads?'] },
    { label: 'Territory & Rivals', prompts: ['How large was their territory at its peak?', 'Compare them to their main rival empire'] },
  ],
  news: [
    { label: 'This Discovery', prompts: ['Summarize this discovery', 'Show me the site on the map'] },
    { label: 'Related', prompts: ['What does the full transcript say about this?', 'Are there similar sites or discoveries?'] },
  ],
}

export default function LyraWelcome({ mode, contextType, onPromptClick, disabled }: LyraWelcomeProps) {
  const isPage = mode === 'page'
  const prompts = CURATED_PROMPTS[contextType] || CURATED_PROMPTS.global

  return (
    <div className={`lyra-welcome-section ${isPage ? 'lyra-welcome-page' : 'lyra-welcome-modal'}`}>
      {/* Hero */}
      <div className="lyra-welcome-hero">
        <div className="lyra-welcome-avatar-wrap">
          <img
            src="/lyra.gif"
            alt="Lyra Whiskerbyte"
            className={`lyra-welcome-avatar ${isPage ? 'lyra-welcome-avatar-lg' : ''}`}
          />
          {isPage && <span className="lyra-welcome-avatar-ring" />}
        </div>
        <div className="lyra-welcome-hero-text">
          <div className="lyra-welcome-name">Lyra Whiskerbyte</div>
          <div className="lyra-welcome-subtitle">Archaeological AI Agent</div>
        </div>
        {isPage && (
          <div className="lyra-welcome-stats">
            <span>1,000,000+ sites</span>
            <span className="lyra-welcome-stats-sep">&middot;</span>
            <span>46 empires</span>
            <span className="lyra-welcome-stats-sep">&middot;</span>
            <span>39 channels</span>
          </div>
        )}
      </div>

      {/* Capability cards */}
      <div className={`lyra-welcome-caps ${isPage ? '' : 'lyra-welcome-caps-compact'}`}>
        {CAPABILITIES.map((cap) => (
          <button
            key={cap.label}
            className={`lyra-welcome-cap-card ${isPage ? '' : 'lyra-welcome-cap-chip'}`}
            onClick={() => onPromptClick(cap.prompt)}
            disabled={disabled}
          >
            <span className="lyra-welcome-cap-icon">{cap.icon}</span>
            <span className="lyra-welcome-cap-label">{cap.label}</span>
            {isPage && <span className="lyra-welcome-cap-desc">{cap.desc}</span>}
          </button>
        ))}
      </div>

      {/* Curated prompts */}
      <div className={`lyra-welcome-prompts ${isPage ? 'lyra-welcome-prompts-grid' : ''}`}>
        {prompts.slice(0, isPage ? 4 : 2).map((cat) => (
          <div key={cat.label} className="lyra-welcome-prompt-group">
            <div className="lyra-welcome-prompt-label">{cat.label}</div>
            {cat.prompts.map((p) => (
              <button
                key={p}
                className="lyra-welcome-prompt-btn"
                onClick={() => onPromptClick(p)}
                disabled={disabled}
              >
                {p}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
