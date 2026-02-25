/**
 * GamePage — Forgotten Worlds card game rules and guide.
 * Static informational page, no auth required.
 */

import { useState } from 'react'
import type { CardData } from '../types/cards'
import { GameCard, EmpireCard } from '../components/cards/GameCard'
import { RARITY_TIERS as RARITY_TIERS_MAP } from '../constants/rarity'
import { SUB_BRANDS, BRAND_ASSETS } from '../constants/brand'
import gameConstants from '../data/game-constants.generated.json'
import PageHeader from '../components/layout/PageHeader'
import '../styles/game.css'

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const STAT_DESCRIPTIONS = [
  { name: 'Antiquity', range: '1–10', desc: 'How old the site is. Gobekli Tepe (10) predates the pyramids.' },
  { name: 'Fortification', range: '1–10', desc: 'Defensibility. Castles and citadels score highest.' },
  { name: 'Cultural Influence', range: '1–10', desc: 'How well-documented and connected the site is.' },
  { name: 'Mystery', range: '1–10', desc: 'How rare and enigmatic. Unique site types score highest.' },
  { name: 'Legacy', range: '1–10', desc: 'Lasting impact: age span, UNESCO status, community engagement.' },
]

const RARITY_DESCRIPTIONS: Record<number, string> = {
  1: 'Well-known sites with standard documentation',
  2: 'Sites with above-average mystery or cultural reach',
  3: 'Significant sites with rich content and history',
  4: 'Extraordinary sites — UNESCO listed, 3D-scanned, or deeply mysterious',
  5: 'The rarest cards — Pompeii, Gobekli Tepe, Machu Picchu',
}

const RARITY_TIERS = [1, 2, 3, 4, 5].map(tier => ({
  tier,
  name: RARITY_TIERS_MAP[tier].name,
  color: RARITY_TIERS_MAP[tier].color,
  desc: RARITY_DESCRIPTIONS[tier],
}))

const CATEGORY_GROUPS = [
  { name: 'Fortifications', icon: '\u{1f3f0}', primary: 'Fortification', beats: 'Settlements' },
  { name: 'Settlements', icon: '\u{1f3d8}\ufe0f', primary: 'Cultural Influence', beats: 'Religious' },
  { name: 'Religious', icon: '\u{1f6d5}', primary: 'Mystery', beats: 'Burial & Death' },
  { name: 'Burial & Death', icon: '\u26b0\ufe0f', primary: 'Antiquity', beats: 'Megalithic' },
  { name: 'Megalithic', icon: '\u{1faa8}', primary: 'Fortification', beats: 'Fortifications' },
  { name: 'Monuments', icon: '\u{1f3db}\ufe0f', primary: 'Legacy', beats: 'Infrastructure' },
  { name: 'Infrastructure', icon: '\u{1f6e4}\ufe0f', primary: 'Legacy', beats: 'Water & Ports' },
  { name: 'Water & Ports', icon: '\u2693', primary: 'Cultural Influence', beats: 'Rock & Cave' },
  { name: 'Rock & Cave', icon: '\u{1faa8}', primary: 'Antiquity', beats: 'Monuments' },
  { name: 'Other', icon: '\u{1f50d}', primary: 'Mystery', beats: '—' },
]

const SYNERGY_TYPES = [
  { name: 'Category Synergy', trigger: '3+ cards from same group', bonus: '+1 to that group\'s primary stat', example: '3 Fortifications \u2192 +1 Fortification to each' },
  { name: 'Crossroads', trigger: '4+ different empires in deck', bonus: '+1/+2 Cultural Influence to ALL', example: '4 empires \u2192 +1 CI, 6 empires \u2192 +2 CI' },
  { name: 'Ancient Anchor', trigger: '2+ pre-empire sites', bonus: '+1 Mystery to anchor cards', example: 'Gobekli Tepe + Stonehenge \u2192 +1 Mystery' },
  { name: 'Temporal Synergy', trigger: '3+ cards from same era', bonus: '+1 Legacy to each', example: '3 Bronze Age sites \u2192 +1 Legacy' },
  { name: 'Cross-Combo', trigger: 'Specific category pair from same country', bonus: '+2 Mystery to both', example: 'Egyptian Religious + Burial & Death \u2192 +2 Mystery' },
  { name: 'Commander', trigger: 'Empire card as Commander + homeland sites', bonus: '+1 thematic stat (max 3 cards)', example: 'Roman Commander \u2192 +1 Fortification to 3 Roman sites' },
  { name: 'Trade Routes', trigger: 'Sites from 2 historically connected empires', bonus: '+1 Legacy to weakest card from each empire (max 3 routes)', example: 'Han + Roman sites \u2192 Silk Road activates \u2192 +1 Legacy' },
  { name: 'Trade Network', trigger: '3 empires all pairwise connected by trade routes', bonus: 'Routes upgrade to +2 Legacy instead of +1', example: 'Han + Roman + Kushan \u2192 Silk Road Network \u2192 +2 Legacy each' },
]

const TRADE_ROUTES_DATA = gameConstants.tradeRoutes

const TRADE_NETWORK_TRIANGLES = [
  { name: 'Silk Road Network', empires: 'Han Dynasty + Roman Empire + Kushan Empire', routes: 'Silk Road + Gandhara Corridor + Kushan Silk Route' },
  { name: 'East African Network', empires: 'Egyptian Kingdom + Kingdom of Kush + Aksumite Empire', routes: 'Nile Corridor + Red Sea Circuit + Nubian Trade' },
  { name: 'Bronze Age Network', empires: 'Babylonian Empire + Hittite Empire + Mycenaean Greece', routes: 'Fertile Crescent Link + Anatolian Bridge + Aegean Bronze Trade' },
]

const PACK_GUARANTEES: Record<string, string> = {
  common: '3 Common+',
  uncommon: '1 Uncommon+, 2 Common+',
  rare: '1 Rare+, 2 Uncommon+, 2 Common+',
  epic: '1 Epic+, 1 Rare+, 3 Common+',
}
const PACK_TIER: Record<string, number> = { common: 1, uncommon: 2, rare: 3, epic: 4 }

const PACKS = Object.entries(gameConstants.packPrices).map(([key, p]) => ({
  name: key.charAt(0).toUpperCase() + key.slice(1),
  cost: p.cost,
  cards: p.cards,
  guarantees: PACK_GUARANTEES[key],
  color: RARITY_TIERS_MAP[PACK_TIER[key]].color,
}))

const EXPEDITIONS = [
  'The Nile Valley', 'The Aegean World', 'Mesoamerican Empires',
  'The Fertile Crescent', 'Stones of Britain', 'The Indus Enigma',
  'Dynasties of the East', 'African Kingdoms', 'Peaks of the Andes', 'Mare Nostrum',
]

const DISCORD_COMMANDS = [
  { cmd: '/card <name>', desc: 'Look up any card\'s stats (shows empire affiliations)' },
  { cmd: '/cards', desc: 'Browse your collection' },
  { cmd: '/pack <type>', desc: 'Open a card pack' },
  { cmd: '/deck', desc: 'View or manage your battle deck (shows commander & synergies)' },
  { cmd: '/duel @player [stake]', desc: 'Challenge someone to battle' },
  { cmd: '/daily', desc: 'Claim daily reward (100 credits + 1 card)' },
  { cmd: '/quiz', desc: 'Start a 5-question archaeology quiz' },
  { cmd: '/expedition', desc: 'Play a themed PvE campaign (earn empire cards!)' },
  { cmd: '/empire <name>', desc: 'View an empire card\'s details and history' },
  { cmd: '/empires', desc: 'List your collected empire cards' },
  { cmd: '/set-commander <empire>', desc: 'Equip a commander to your active deck' },
  { cmd: '/leaderboard', desc: 'View top players' },
]

// ---------------------------------------------------------------------------
// Card Mockup data (using CardData shape for the unified GameCard component)
// ---------------------------------------------------------------------------

interface MockupCardExt extends CardData {
  bonuses?: Partial<Record<string, number>>
  description?: string
  coords?: string
  typeBadgeColor?: string
  periodBadgeColor?: string
  dupsFilled?: number
}

const MOCKUP_CARDS: MockupCardExt[] = [
  {
    site_id: 'mockup-gobekli', name: 'Gobekli Tepe', country: 'Turkey',
    period_name: '< 4500 BC', period_start: -10000, site_type: 'Temple',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/d/d5/G%C3%B6bekli_Tepe%2C_Urfa.jpg',
    antiquity: 10, fortification: 3, cultural_influence: 9, mystery: 10, legacy: 8,
    total_power: 40, rarity_tier: 5, rarity_name: 'Legendary',
    category_group: 'Religious', civilization: null, star_level: 5, card_xp: 0,
    bonuses: { fortification: 2, cultural_influence: 1, legacy: 2 },
    typeBadgeColor: '#e6b800', periodBadgeColor: '#ff0000',
    coords: '37.2233\u00b0 N, 38.9224\u00b0 E',
    description: 'A Neolithic archaeological site comprising of a number of large circular structures supported by massive stone pillars \u2014 many richly decorated with abstract anthropomorphic details and animal reliefs.',
    dupsFilled: 0,
  },
  {
    site_id: 'mockup-machu', name: 'Machu Picchu', country: 'Peru',
    period_name: '1000 - 1500 AD', period_start: 1450, site_type: 'Fortress/Citadel',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/1/13/Before_Machu_Picchu.jpg',
    antiquity: 2, fortification: 10, cultural_influence: 9, mystery: 8, legacy: 9,
    total_power: 38, rarity_tier: 5, rarity_name: 'Legendary',
    category_group: 'Fortifications', civilization: null, star_level: 4, card_xp: 0,
    bonuses: { antiquity: 1, cultural_influence: 1, mystery: 1, legacy: 1 },
    typeBadgeColor: '#dd1111', periodBadgeColor: '#ffdd00',
    coords: '13.1631\u00b0 S, 72.5450\u00b0 W',
    description: 'An ancient Inca citadel located on a 2,430 metre mountain range. Often referred to as the "Lost City of the Incas", it is the most familiar icon of Inca civilization.',
    dupsFilled: 9,
  },
  {
    site_id: 'mockup-karnak', name: 'Karnak Temple Complex', country: 'Egypt',
    period_name: '3000 - 1500 BC', period_start: -2000, site_type: 'Temple Complex',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/f/f2/Karnak_Temples.jpg',
    antiquity: 8, fortification: 3, cultural_influence: 9, mystery: 7, legacy: 8,
    total_power: 35, rarity_tier: 4, rarity_name: 'Epic',
    category_group: 'Religious', civilization: null, star_level: 3, card_xp: 0,
    bonuses: { antiquity: 1, cultural_influence: 1, legacy: 1 },
    typeBadgeColor: '#ffc300', periodBadgeColor: '#ff4400',
    coords: '25.7188\u00b0 N, 32.6573\u00b0 E',
    description: 'The Karnak Temple Complex comprises a vast mix of decayed temples, pylons, chapels, and other buildings near Luxor. Construction began during the reign of Senusret I.',
    dupsFilled: 5,
  },
  {
    site_id: 'mockup-chichen', name: 'Chichen Itza', country: 'Mexico',
    period_name: '500 - 1000 AD', period_start: 600, site_type: 'Pyramid Complex',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/5/51/Chichen_Itza_3.jpg',
    antiquity: 4, fortification: 7, cultural_influence: 9, mystery: 8, legacy: 7,
    total_power: 35, rarity_tier: 4, rarity_name: 'Epic',
    category_group: 'Monuments', civilization: null, star_level: 2, card_xp: 0,
    bonuses: { cultural_influence: 1, mystery: 1 },
    typeBadgeColor: '#dd2277', periodBadgeColor: '#ffcc00',
    coords: '20.6843\u00b0 N, 88.5678\u00b0 W',
    description: 'A large pre-Columbian city built by the Maya people. Its most iconic structure is the step pyramid known as El Castillo, one of the New Seven Wonders of the World.',
    dupsFilled: 3,
  },
  {
    site_id: 'mockup-knossos', name: 'Knossos', country: 'Greece',
    period_name: '< 4500 BC', period_start: -7000, site_type: 'Settlement',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/8/8e/Armon_Knossos_P1060093.JPG',
    antiquity: 10, fortification: 5, cultural_influence: 7, mystery: 6, legacy: 5,
    total_power: 33, rarity_tier: 3, rarity_name: 'Rare',
    category_group: 'Settlements', civilization: null, star_level: 1, card_xp: 0,
    bonuses: { cultural_influence: 1 },
    typeBadgeColor: '#ff5500', periodBadgeColor: '#ff0000',
    coords: '35.2981\u00b0 N, 25.1631\u00b0 E',
    description: 'A Bronze Age archaeological site in Crete. The site was a major center of the Minoan civilization, known for its association with the myth of Theseus and the Minotaur.',
    dupsFilled: 1,
  },
  {
    site_id: 'mockup-uxmal', name: 'Uxmal', country: 'Mexico',
    period_name: '500 - 1000 AD', period_start: 700, site_type: 'Settlement',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/e/e5/Uxmal_Pyramid_of_the_Magician.jpg',
    antiquity: 4, fortification: 5, cultural_influence: 8, mystery: 7, legacy: 4,
    total_power: 28, rarity_tier: 3, rarity_name: 'Rare',
    category_group: 'Settlements', civilization: null, star_level: 1, card_xp: 0,
    bonuses: { cultural_influence: 1 },
    typeBadgeColor: '#ff5500', periodBadgeColor: '#ffcc00',
    coords: '20.3594\u00b0 N, 89.7714\u00b0 W',
    description: 'An ancient Maya city of the classical period located in present-day Mexico. It is considered one of the most important archaeological sites of Maya culture.',
    dupsFilled: 2,
  },
  {
    site_id: 'mockup-newgrange', name: 'Newgrange', country: 'Ireland',
    period_name: '4500 - 3000 BC', period_start: -3200, site_type: 'Necropolis',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/0/0f/Irelands_history.jpg',
    antiquity: 9, fortification: 2, cultural_influence: 5, mystery: 4, legacy: 3,
    total_power: 23, rarity_tier: 2, rarity_name: 'Uncommon',
    category_group: 'Burial & Death', civilization: null, star_level: 0, card_xp: 0,
    typeBadgeColor: '#8833dd', periodBadgeColor: '#ff2200',
    coords: '53.6947\u00b0 N, 6.4756\u00b0 W',
    description: 'A Prehistoric monument in County Meath. It is an exceptionally grand passage tomb built during the Neolithic Period, around 3200 BC, overlooking the River Boyne.',
    dupsFilled: 1,
  },
  {
    site_id: 'mockup-pompeii', name: 'Amphitheatre of Pompeii', country: 'Italy',
    period_name: '500 BC - 1 AD', period_start: -70, site_type: 'Megalithic',
    thumbnail_url: 'https://upload.wikimedia.org/wikipedia/commons/8/80/Ancient_Roman_Pompeii_-_Pompeji_-_Campania_-_Italy_-_July_10th_2013_-_45.jpg',
    antiquity: 5, fortification: 8, cultural_influence: 3, mystery: 1, legacy: 1,
    total_power: 18, rarity_tier: 1, rarity_name: 'Common',
    category_group: 'Megalithic', civilization: null, star_level: 0, card_xp: 0,
    typeBadgeColor: '#0066bb', periodBadgeColor: '#ff8800',
    coords: '40.7508\u00b0 N, 14.4869\u00b0 E',
    description: 'One of the oldest surviving Roman amphitheatres, located in the ancient city of Pompeii near Naples. Buried by the eruption of Mount Vesuvius in 79 AD.',
    dupsFilled: 0,
  },
]

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------

type SectionId = 'overview' | 'cards' | 'types' | 'empires' | 'synergies' | 'battles' | 'packs' | 'quiz' | 'expeditions' | 'evolution' | 'economy' | 'discord'

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'cards', label: 'Cards & Stats' },
  { id: 'types', label: 'Type Advantage' },
  { id: 'empires', label: 'Empire Cards' },
  { id: 'synergies', label: 'Deck Synergies' },
  { id: 'battles', label: 'Battles' },
  { id: 'packs', label: 'Card Packs' },
  { id: 'quiz', label: 'Quiz Mode' },
  { id: 'expeditions', label: 'Expeditions' },
  { id: 'evolution', label: 'Card Evolution' },
  { id: 'economy', label: 'Economy' },
  { id: 'discord', label: 'Discord Commands' },
]

function OverviewSection() {
  return (
    <section className="game-section" id="overview">
      <h2>What is Forgotten Worlds?</h2>
      <p>
        Forgotten Worlds is a collectible card game where every card is a <strong>real archaeological site</strong>.
        Collect from over 3,900 sites spanning every continent and 10,000 years of human history — from
        Gobekli Tepe to Machu Picchu, from Stonehenge to Great Zimbabwe.
      </p>
      <div className="game-highlights">
        <div className="game-highlight">
          <span className="game-highlight-icon">{'\u{1f0cf}'}</span>
          <strong>Collect</strong>
          <span>Open packs, claim dailies, earn cards through quizzes and battles</span>
        </div>
        <div className="game-highlight">
          <span className="game-highlight-icon">{'\u{1f9e9}'}</span>
          <strong>Build</strong>
          <span>Craft synergy decks — combine region, era, and category for stat bonuses</span>
        </div>
        <div className="game-highlight">
          <span className="game-highlight-icon">{'\u2694\ufe0f'}</span>
          <strong>Battle</strong>
          <span>Challenge other players or NPC expeditions. Snap to double the stakes.</span>
        </div>
        <div className="game-highlight">
          <span className="game-highlight-icon">{'\u{1f4da}'}</span>
          <strong>Learn</strong>
          <span>Every card teaches you about a real place. Quizzes reward archaeological knowledge.</span>
        </div>
      </div>
      <div className="game-cta-row">
        <a href="/cards.html" className="game-cta-btn">Open Your Collection</a>
      </div>
    </section>
  )
}

function CardsSection() {
  return (
    <section className="game-section" id="cards">
      <h2>Cards & Stats</h2>
      <p>
        Each card represents a real archaeological site with 5 stats computed from actual data — age, defensibility,
        documentation depth, rarity, and lasting impact.
      </p>

      <div className="game-cards-showcase">
        {MOCKUP_CARDS.map(card => (
          <GameCard
            key={card.site_id}
            card={card}
            variant="showcase"
            bonuses={card.bonuses}
            description={card.description}
            coords={card.coords}
            typeBadgeColor={card.typeBadgeColor}
            periodBadgeColor={card.periodBadgeColor}
            dupsFilled={card.dupsFilled}
          />
        ))}
      </div>

      <div className="game-stats-table">
        <table>
          <thead><tr><th>Stat</th><th>Range</th><th>What it measures</th></tr></thead>
          <tbody>
            {STAT_DESCRIPTIONS.map(s => (
              <tr key={s.name}>
                <td className="game-stat-name">{s.name}</td>
                <td>{s.range}</td>
                <td>{s.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p><strong>Total Power</strong> = sum of all 5 stats (max 50).</p>

      <h3>Rarity Tiers</h3>
      <p>Rarity is based on mystery, cultural influence, UNESCO status, content variety, and 3D model availability.</p>
      <div className="game-rarity-list">
        {RARITY_TIERS.map(r => (
          <div key={r.tier} className="game-rarity-item" style={{ borderLeftColor: r.color }}>
            <span className="game-rarity-name" style={{ color: r.color }}>{r.name}</span>
            <span className="game-rarity-desc">{r.desc}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function TypeAdvantageSection() {
  return (
    <section className="game-section" id="types">
      <h2>Category Groups & Type Advantage</h2>
      <p>
        Every site belongs to one of 10 category groups. Each group has a <strong>primary stat</strong> (boosted by synergies)
        and a <strong>type advantage</strong> — when your card's group beats the opponent's, it gets <strong>+2</strong> to
        the compared stat.
      </p>
      <div className="game-types-table">
        <table>
          <thead>
            <tr><th>Group</th><th>Primary Stat</th><th>Beats</th></tr>
          </thead>
          <tbody>
            {CATEGORY_GROUPS.map(g => (
              <tr key={g.name}>
                <td><span className="game-type-icon">{g.icon}</span> {g.name}</td>
                <td>{g.primary}</td>
                <td className="game-beats">{g.beats}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="game-advantage-note">
        <strong>Two advantage wheels:</strong> Fortifications {'\u2192'} Settlements {'\u2192'} Religious {'\u2192'} Burial & Death {'\u2192'} Megalithic {'\u2192'} Fortifications.
        And: Monuments {'\u2192'} Infrastructure {'\u2192'} Water & Ports {'\u2192'} Rock & Cave {'\u2192'} Monuments.
      </div>
    </section>
  )
}

const EMPIRE_EXAMPLES = [
  { name: 'Roman Empire', stat: 'Fortification', flavor: 'Military engineering', period: '509 BCE \u2013 476 CE' },
  { name: 'Egyptian Kingdom', stat: 'Mystery', flavor: 'Enigmatic monuments', period: '3100 BCE \u2013 30 BCE' },
  { name: 'Greek City-States', stat: 'Cultural Influence', flavor: 'Philosophy & democracy', period: '800 BCE \u2013 338 BCE' },
  { name: 'Han Dynasty', stat: 'Legacy', flavor: 'Bureaucratic continuity', period: '206 BCE \u2013 220 CE' },
  { name: 'Maurya Empire', stat: 'Cultural Influence', flavor: 'Ashoka\'s edicts', period: '322 BCE \u2013 185 BCE' },
  { name: 'Akkadian Empire', stat: 'Antiquity', flavor: 'First empire in history', period: '2334 BCE \u2013 2154 BCE' },
]

// ---------------------------------------------------------------------------
// Empire Card Mockup data
// ---------------------------------------------------------------------------

interface EmpireMockup {
  id: string
  name: string
  region: string
  period: string
  thematicStat: string
  statIcon: string
  statColor: string
  desc: string
  color: string
  colorGlow: string
}

const EMPIRE_MOCKUP_CARDS: EmpireMockup[] = [
  {
    id: 'roman',
    name: 'Roman Empire',
    region: 'Mediterranean',
    period: '509 BCE \u2013 476 CE',
    thematicStat: 'Fortification',
    statIcon: '\u2694',
    statColor: '#e55555',
    desc: 'From a small city-state on the Tiber to the greatest empire of antiquity. Roman engineering, law, and military organization shaped Western civilization for millennia.',
    color: '#c02023',
    colorGlow: 'rgba(192, 32, 35, 0.25)',
  },
  {
    id: 'egyptian',
    name: 'Egyptian Kingdom',
    region: 'Ancient Near East',
    period: '3100 BCE \u2013 30 BCE',
    thematicStat: 'Mystery',
    statIcon: '\u2754',
    statColor: '#33dddd',
    desc: 'For 3,000 years the pharaohs ruled the Nile Valley, building monuments that still astound. Egyptian religion, writing, and architecture influenced all subsequent Mediterranean civilizations.',
    color: '#e6b800',
    colorGlow: 'rgba(230, 184, 0, 0.25)',
  },
  {
    id: 'greek',
    name: 'Greek City-States',
    region: 'Mediterranean',
    period: '1050 BCE \u2013 80 CE',
    thematicStat: 'Cultural Influence',
    statIcon: '\u2605',
    statColor: '#ff6eb4',
    desc: 'The Greek city-states pioneered democracy, philosophy, theater, and the Olympic Games. Their intellectual legacy forms the foundation of Western thought.',
    color: '#2196F3',
    colorGlow: 'rgba(33, 150, 243, 0.25)',
  },
  {
    id: 'han',
    name: 'Han Dynasty',
    region: 'East Asia',
    period: '206 BCE \u2013 220 CE',
    thematicStat: 'Legacy',
    statIcon: '\u{1f3c6}',
    statColor: '#aa66ee',
    desc: 'The Han Dynasty consolidated China into a unified empire with a centralized bureaucracy, the Silk Road, and advances in papermaking that changed the world.',
    color: '#b71c1c',
    colorGlow: 'rgba(183, 28, 28, 0.25)',
  },
  {
    id: 'akkadian',
    name: 'Akkadian Empire',
    region: 'Ancient Near East',
    period: '2334 BCE \u2013 2154 BCE',
    thematicStat: 'Antiquity',
    statIcon: '\u23f1',
    statColor: '#ffaa33',
    desc: 'The world\'s first empire, founded by Sargon of Akkad around 2334 BCE. It united Mesopotamia under a single ruler for the first time.',
    color: '#cd7f32',
    colorGlow: 'rgba(205, 127, 50, 0.25)',
  },
  {
    id: 'inca',
    name: 'Inca Empire',
    region: 'Americas',
    period: '1438 CE \u2013 1533 CE',
    thematicStat: 'Fortification',
    statIcon: '\u2694',
    statColor: '#e55555',
    desc: 'Without wheels, iron, or written language, the Inca built 40,000 km of roads across extreme mountain terrain and administered the largest empire in pre-Columbian America.',
    color: '#4CAF50',
    colorGlow: 'rgba(76, 175, 80, 0.25)',
  },
]

function EmpiresSection() {
  return (
    <section className="game-section" id="empires">
      <h2>Empire Cards & Commander</h2>
      <p>
        Empire Cards are <strong>separate collectibles</strong> from site cards. Each represents a historical civilization
        with educational content about its history, territory, and cultural impact. Earn them by completing expeditions.
      </p>

      <div className="empire-cards-showcase">
        {EMPIRE_MOCKUP_CARDS.map(e => (
          <EmpireCard key={e.id} empire={e} />
        ))}
      </div>

      <h3>How to Earn Empire Cards</h3>
      <p>
        Each expedition rewards a specific empire card upon completion. For example, completing "Mare Nostrum" awards the
        Roman Empire card, while "The Nile Valley" awards the Egyptian Kingdom card. The "Stones of Britain" expedition
        awards no empire card — those sites predate empires.
      </p>

      <h3>Commander Slot</h3>
      <p>
        Decks get an <strong>optional Commander slot</strong> (separate from your 10 site cards). Set an empire card as
        your Commander with <code>/set-commander</code>. No commander = no penalty — decks work fine without one.
      </p>
      <div className="game-advantage-note">
        <strong>Commander Bonus ("Homeland"):</strong> Sites in your deck that fall within the Commander's historical
        borders get <strong>+1 to the empire's thematic stat</strong>, capped at <strong>3 cards max</strong>.
        Even with 10 Roman sites, only the 3 with the highest base value in that stat get the bonus.
      </div>

      <h3>Empire Thematic Stats</h3>
      <div className="game-stats-table">
        <table>
          <thead><tr><th>Empire</th><th>Period</th><th>Thematic Stat</th><th>Flavor</th></tr></thead>
          <tbody>
            {EMPIRE_EXAMPLES.map(e => (
              <tr key={e.name}>
                <td className="game-stat-name">{e.name}</td>
                <td>{e.period}</td>
                <td>{e.stat}</td>
                <td>{e.flavor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Why the 3-Card Cap Matters</h3>
      <p>
        The cap kills the incentive to mono-stack. You only need 3 "home" sites to max the commander bonus — then
        the remaining 7 slots should be diverse to hit the <strong>Crossroads</strong> synergy threshold. This naturally
        rewards global variety: you <em>want</em> sites from Egypt, China, Mesoamerica, and Africa alongside your Roman core.
      </p>

      <h3>Optimal Deck Shape</h3>
      <ul className="game-combo-list">
        <li><strong>1 Commander</strong> (e.g., Roman Empire)</li>
        <li><strong>3 homeland sites</strong> within Roman borders (+1 Fortification each)</li>
        <li><strong>5-7 diverse sites</strong> spanning 3-5 other empires (Crossroads bonus)</li>
        <li><strong>0-2 pre-empire sites</strong> (Ancient Anchor bonus if 2+)</li>
      </ul>
    </section>
  )
}

function SynergiesSection() {
  return (
    <section className="game-section" id="synergies">
      <h2>Deck Synergies</h2>
      <p>
        The real strategy is in deck building. Cards that share a category or era, span diverse empires, or include
        pre-empire sites all grant permanent stat bonuses. The Commander system adds another layer — rewarding
        a core of "homeland" sites alongside geographic diversity.
      </p>
      <div className="game-synergy-grid">
        {SYNERGY_TYPES.map(s => (
          <div key={s.name} className="game-synergy-card">
            <h4>{s.name}</h4>
            <div className="game-synergy-trigger">{s.trigger}</div>
            <div className="game-synergy-bonus">{s.bonus}</div>
            <div className="game-synergy-example">{s.example}</div>
          </div>
        ))}
      </div>
      <h3>Cross-Combo Pairs</h3>
      <p>These specific category pairs from the same country trigger +2 Mystery to both cards:</p>
      <ul className="game-combo-list">
        <li><strong>Sacred Burial Grounds:</strong> Religious + Burial & Death</li>
        <li><strong>City-Fortress Complexes:</strong> Settlements + Fortifications</li>
        <li><strong>Engineering Marvels:</strong> Water & Ports + Infrastructure</li>
        <li><strong>Ritual Stone Circles:</strong> Megalithic + Religious</li>
        <li><strong>Civic Centers:</strong> Monuments + Settlements</li>
      </ul>

      <h3>Trade Routes</h3>
      <p>
        23 named historical trade connections between empire pairs. If your deck has at least 1 site from
        each empire in a pair, the route activates and gives <strong>+1 Legacy</strong> to the weakest card
        from each empire. Max <strong>3 routes</strong> per deck.
      </p>
      <div className="game-trade-routes-grid">
        {TRADE_ROUTES_DATA.map(r => (
          <div key={r.name} className="game-trade-route">
            <strong>{r.name}</strong>
            <span className="game-trade-route-empires">{r.empireA} {'\u2194'} {r.empireB}</span>
            <span className="game-trade-route-goods">{r.goods}</span>
          </div>
        ))}
      </div>

      <h3>Trade Networks</h3>
      <p>
        When 3 empires in your deck are <strong>all pairwise connected</strong> by trade routes (forming a triangle),
        those routes give <strong>+2 Legacy</strong> instead of +1. Triangle routes are selected first when choosing
        which 3 routes to activate.
      </p>
      <div className="game-synergy-grid">
        {TRADE_NETWORK_TRIANGLES.map(t => (
          <div key={t.name} className="game-synergy-card">
            <h4>{t.name}</h4>
            <div className="game-synergy-trigger">{t.empires}</div>
            <div className="game-synergy-bonus">+2 Legacy per route (3 routes = +6 total)</div>
            <div className="game-synergy-example">{t.routes}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function BattlesSection() {
  return (
    <section className="game-section" id="battles">
      <h2>Battles</h2>
      <p>
        Battles are 5 rounds. Each round compares one stat (randomly chosen). Build a well-rounded deck to cover all stats.
      </p>
      <div className="game-battle-steps">
        <div className="game-step">
          <span className="game-step-num">1</span>
          <div>
            <strong>Shuffle & Synergy</strong>
            <p>Both decks are shuffled. Synergy bonuses are computed and locked in for the battle.</p>
          </div>
        </div>
        <div className="game-step">
          <span className="game-step-num">2</span>
          <div>
            <strong>5 Random Stats</strong>
            <p>The 5 stats are placed in random order. Each round uses one: Antiquity, Fortification, Cultural Influence, Mystery, or Legacy.</p>
          </div>
        </div>
        <div className="game-step">
          <span className="game-step-num">3</span>
          <div>
            <strong>Compare Cards</strong>
            <p>Each round, the top card from each deck is compared on that round's stat. Synergy bonuses and type advantage (+2) are added. Higher value wins the round.</p>
          </div>
        </div>
        <div className="game-step">
          <span className="game-step-num">4</span>
          <div>
            <strong>Antiquity Special</strong>
            <p>If the Antiquity stat round is won, the winner <em>removes the opponent's next card</em> from battle. Ancient sites are powerful.</p>
          </div>
        </div>
        <div className="game-step">
          <span className="game-step-num">5</span>
          <div>
            <strong>Winner</strong>
            <p>Most rounds won out of 5 wins the battle. Tiebreaker: higher antiquity stat. Winner earns 25 credits, 25 XP, and a 10% chance at a random card drop.</p>
          </div>
        </div>
      </div>

      <h3>Staked Battles</h3>
      <p>
        Challenge with <code>/duel @player [stake]</code> — the stake is the credits each player puts up.
        Both players must be able to afford it, and the maximum stake is <strong>50,000 credits</strong>.
        The defender can always <strong>decline</strong> — nobody gets forced into a bet they don't want.
        Winner takes the entire pot (2x the stake) plus the standard 25 credit battle reward.
      </p>

      <h3>Snap Mechanic</h3>
      <p>
        In staked battles, after seeing the first 2 rounds, either player can <strong>Snap</strong> to double the stakes.
        The opponent must <strong>Accept</strong> (continue at 2x stakes) or <strong>Retreat</strong> (forfeit at original stakes).
        If either player can't afford the doubled stake, the snap is cancelled and the battle continues at the original amount.
        This creates a poker-like bluffing layer — do you snap when you're ahead, or bluff when you're behind?
      </p>
    </section>
  )
}

function PacksSection() {
  return (
    <section className="game-section" id="packs">
      <h2>Card Packs</h2>
      <p>Spend Lyra credits to open packs and add new sites to your collection.</p>
      <div className="game-packs-grid">
        {PACKS.map(p => (
          <div key={p.name} className="game-pack" style={{ borderColor: p.color }}>
            <div className="game-pack-name" style={{ color: p.color }}>{p.name}</div>
            <div className="game-pack-cost">{p.cost.toLocaleString()} credits</div>
            <div className="game-pack-cards">{p.cards} cards</div>
            <div className="game-pack-guarantees">{p.guarantees}</div>
          </div>
        ))}
      </div>
      <p className="game-note">
        Packs prefer giving you cards you don't own yet. If you get a duplicate, it feeds into card evolution instead.
      </p>

      <h3>How Rarity Rolls Work</h3>
      <p>
        Each card slot has a <strong>minimum guaranteed rarity</strong>. The actual rarity is then rolled
        using weighted odds — so even a Common+ slot can land an Epic or Legendary, just at lower probability.
        Higher-tier guarantees filter out lower rarities, making the remaining rolls more concentrated toward the top.
      </p>

      <h3>Per-Slot Odds</h3>
      <div className="game-stats-table">
        <table>
          <thead>
            <tr><th>Guarantee</th><th>Common</th><th>Uncommon</th><th>Rare</th><th>Epic</th><th>Legendary</th></tr>
          </thead>
          <tbody>
            <tr><td>Common+</td><td>47.7%</td><td>31.8%</td><td>15.9%</td><td>4.2%</td><td className="game-legendary-cell">0.35%</td></tr>
            <tr><td>Uncommon+</td><td>—</td><td>60.8%</td><td>30.4%</td><td>8.1%</td><td className="game-legendary-cell">0.67%</td></tr>
            <tr><td>Rare+</td><td>—</td><td>—</td><td>77.6%</td><td>20.7%</td><td className="game-legendary-cell">1.7%</td></tr>
            <tr><td>Epic+</td><td>—</td><td>—</td><td>—</td><td>92.4%</td><td className="game-legendary-cell">7.6%</td></tr>
          </tbody>
        </table>
      </div>

      <h3>Legendary Odds per Pack</h3>
      <div className="game-stats-table">
        <table>
          <thead>
            <tr><th>Pack</th><th>Cost</th><th>At Least 1 Legendary</th><th>Approx.</th></tr>
          </thead>
          <tbody>
            <tr><td style={{ color: RARITY_TIERS_MAP[1].color }}>Common</td><td>500</td><td className="game-legendary-cell">~1%</td><td>~1 in 96</td></tr>
            <tr><td style={{ color: RARITY_TIERS_MAP[2].color }}>Uncommon</td><td>1,500</td><td className="game-legendary-cell">~1.4%</td><td>~1 in 73</td></tr>
            <tr><td style={{ color: RARITY_TIERS_MAP[3].color }}>Rare</td><td>5,000</td><td className="game-legendary-cell">~3.7%</td><td>~1 in 27</td></tr>
            <tr><td style={{ color: RARITY_TIERS_MAP[4].color }}>Epic</td><td>15,000</td><td className="game-legendary-cell">~10%</td><td>~1 in 10</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}

function QuizSection() {
  return (
    <section className="game-section" id="quiz">
      <h2>Quiz Mode</h2>
      <p>
        The most direct "learning by playing" mechanic. Answer 5 archaeology questions generated from real card data.
        This isn't trivia — it's active recall from the same database your cards come from.
      </p>
      <div className="game-quiz-types">
        <div className="game-quiz-type"><strong>Age Comparison</strong> — "Which is older: Karnak or Knossos?"</div>
        <div className="game-quiz-type"><strong>Country ID</strong> — "What country is Machu Picchu in?"</div>
        <div className="game-quiz-type"><strong>Category Classification</strong> — "What type of site is Newgrange?"</div>
        <div className="game-quiz-type"><strong>Stat Challenge</strong> — "Which has higher Mystery: Gobekli Tepe or Pompeii?"</div>
        <div className="game-quiz-type"><strong>Period Knowledge</strong> — "What period does Persepolis belong to?"</div>
      </div>
      <div className="game-rewards-box">
        <h4>Rewards</h4>
        <ul>
          <li>+10 credits per correct answer</li>
          <li>+5 XP per correct answer</li>
          <li>Perfect score (5/5): bonus Common card</li>
          <li>Up to 3 quizzes per day</li>
        </ul>
      </div>
    </section>
  )
}

function ExpeditionsSection() {
  return (
    <section className="game-section" id="expeditions">
      <h2>Expeditions (PvE)</h2>
      <p>
        Solo campaigns where you battle <strong>Lyra</strong> — the AI archaeologist who curates decks themed by region.
        Each expedition has 5 stages of increasing difficulty, with archaeological lore between stages.
      </p>
      <div className="game-expeditions-list">
        {EXPEDITIONS.map(name => (
          <span key={name} className="game-expedition-tag">{name}</span>
        ))}
      </div>
      <div className="game-expedition-details">
        <p><strong>How it works:</strong> Pick an expedition and play your active deck against Lyra's regionally themed decks.
          Early stages use Common/Uncommon cards; the final stage fields Rare+ decks.</p>
        <p><strong>Stage rewards:</strong> 15 credits + 15 XP per win.</p>
        <p><strong>Completion reward:</strong> Free Uncommon Pack + an <strong>Empire Card</strong> for that region's civilization!</p>
        <p><strong>Lore:</strong> Between stages, Lyra shares a real fact about that region's archaeology.</p>
      </div>
    </section>
  )
}

function EvolutionSection() {
  return (
    <section className="game-section" id="evolution">
      <h2>Card Evolution</h2>
      <p>
        Duplicate cards aren't wasted — they feed evolution XP into the card you already own.
        At XP thresholds, cards evolve to higher star levels and unlock permanent stat bonuses
        that you assign in the <strong>Deck Builder</strong>.
      </p>
      <div className="game-stars-table">
        <table>
          <thead><tr><th>Star Level</th><th>Duplicates Needed</th><th>Bonus</th></tr></thead>
          <tbody>
            <tr>
              <td className="game-star game-star-1">{'\u2605'}</td>
              <td>2 duplicates</td>
              <td>+1 to any stat (you choose)</td>
            </tr>
            <tr>
              <td className="game-star game-star-2">{'\u2605\u2605'}</td>
              <td>+3 more (5 total)</td>
              <td>+1 to another stat (cumulative)</td>
            </tr>
            <tr>
              <td className="game-star game-star-3">{'\u2605\u2605\u2605'}</td>
              <td>+5 more (10 total)</td>
              <td>+1 to another stat (cumulative)</td>
            </tr>
            <tr>
              <td className="game-star game-star-3">{'\u2605\u2605\u2605\u2605'}</td>
              <td>+8 more (18 total)</td>
              <td>+1 to another stat (cumulative)</td>
            </tr>
            <tr>
              <td className="game-star game-star-3">{'\u2605\u2605\u2605\u2605\u2605'}</td>
              <td>+13 more (31 total)</td>
              <td>+1 to another stat (cumulative)</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="game-evolution-note">
        <h4>How to assign bonuses</h4>
        <p>
          When a card reaches a new star level, go to the <strong>Deck Builder</strong> to choose which stat gets the +1 bonus.
          No stat can exceed 10 — if you pick a stat already at 10, you'll be prompted to choose a different one.
          Bonuses are permanent and shown as a <span className="game-evolution-glow">glowing green</span> bar segment on the card.
        </p>
      </div>
    </section>
  )
}

function EconomySection() {
  return (
    <section className="game-section" id="economy">
      <h2>Credits Economy</h2>
      <p>All card game activities use Lyra credits, the same currency used across Ancient Nerds.</p>
      <div className="game-economy-grid">
        <div className="game-econ-group">
          <h4>Earning Credits</h4>
          <ul>
            <li>Daily reward: <strong>100 credits</strong> + 1 card</li>
            <li>Battle win: <strong>25 credits</strong></li>
            <li>Quiz correct answer: <strong>10 credits</strong></li>
            <li>Expedition stage win: <strong>15 credits</strong></li>
            <li>Staked battle: winner takes the pot</li>
          </ul>
        </div>
        <div className="game-econ-group">
          <h4>Spending Credits</h4>
          <ul>
            <li>Common Pack: <strong>500</strong></li>
            <li>Uncommon Pack: <strong>1,500</strong></li>
            <li>Rare Pack: <strong>5,000</strong></li>
            <li>Epic Pack: <strong>15,000</strong></li>
            <li>Battle stakes: up to <strong>50,000</strong></li>
          </ul>
        </div>
        <div className="game-econ-group">
          <h4>Streak Bonuses</h4>
          <ul>
            <li>Every 3 days: <strong>+150 credits</strong></li>
            <li>Every 7 days: <strong>Free Uncommon Pack</strong></li>
            <li>14-day streak: <strong>+500 credits</strong></li>
            <li>30-day streak: <strong>Free Rare Pack</strong></li>
          </ul>
        </div>
      </div>
    </section>
  )
}

function DiscordSection() {
  return (
    <section className="game-section" id="discord">
      <h2>Discord Commands</h2>
      <p>Play Forgotten Worlds directly in the Ancient Nerds Discord server.</p>
      <div className="game-discord-table">
        <table>
          <thead><tr><th>Command</th><th>Description</th></tr></thead>
          <tbody>
            {DISCORD_COMMANDS.map(c => (
              <tr key={c.cmd}>
                <td className="game-cmd"><code>{c.cmd}</code></td>
                <td>{c.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="game-cta-row">
        <a href="/cards.html" className="game-cta-btn">Open Your Collection</a>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export default function GamePage() {
  const [activeSection, setActiveSection] = useState<SectionId>('overview')

  const scrollTo = (id: SectionId) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="game-page">
      <PageHeader currentPage="game" speechBubble="Every card is a real archaeological site. Collect them, build synergy decks, and battle your friends!">
        <span className="page-header-title">Card Game</span>
      </PageHeader>

      <div className="game-layout">
        <nav className="game-toc">
          <div className="game-toc-label">Contents</div>
          {SECTIONS.map(s => (
            <button
              key={s.id}
              className={`game-toc-link${activeSection === s.id ? ' active' : ''}`}
              onClick={() => scrollTo(s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <main className="game-content">
          <div className="game-logo-wrap">
            <img src={BRAND_ASSETS.forgottenWorldsLogo} alt={`Ancient Nerds: ${SUB_BRANDS.forgottenWorlds}`} className="game-logo" />
            <span className="game-coming-soon">COMING SOON</span>
          </div>
          <OverviewSection />
          <CardsSection />
          <TypeAdvantageSection />
          <EmpiresSection />
          <SynergiesSection />
          <BattlesSection />
          <PacksSection />
          <QuizSection />
          <ExpeditionsSection />
          <EvolutionSection />
          <EconomySection />
          <DiscordSection />
        </main>
      </div>
    </div>
  )
}
