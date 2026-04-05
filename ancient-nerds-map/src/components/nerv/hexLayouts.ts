export type HexState = 'done' | 'run' | 'fail' | 'schd' | 'src' | 'src-done' | 'sink' | 'sink-done' | 'idle';
export type HexDataType = 'llm' | 'db';
export type RagPhase = 'R' | 'A' | 'G';

export interface HexNodeConfig {
  id: string;
  label: string;
  icon: string;
  dataType: HexDataType;
  stepNumber: string;
  position: { left: number; top: number };
  ragPhase?: RagPhase;
}

export interface HexLayoutConfig {
  pipeline: 'news' | 'radar' | 'article';
  hiveWidth: number;
  hiveHeight: number;
  nodes: HexNodeConfig[];
  sourceNode: HexNodeConfig;
  sinkNodes: HexNodeConfig[];
}

// News pipeline: fetch -> retry -> summarize -> match -> posts -> verify -> rescore -> dedup -> screenshots -> backfill
// 4-column snake: Row 0 L→R, Row 1 R→L (staggered), Row 2 L→R, Row 3 sinks
// Hexes 110×128, center-to-center 112px horiz, 98px vert, stagger offset 56px
export const NEWS_LAYOUT: HexLayoutConfig = {
  pipeline: 'news',
  hiveWidth: 450,
  hiveHeight: 424,
  sourceNode: { id: '_source', label: 'Source', icon: '\u25BD', dataType: 'db', stepNumber: 'SRC', position: { left: 0, top: 0 } },
  sinkNodes: [
    { id: '_feed', label: 'Feed', icon: '\u2261', dataType: 'db', stepNumber: 'OUT', position: { left: 56, top: 294 } },
    { id: '_globe', label: 'Globe', icon: '\u2295', dataType: 'db', stepNumber: 'OUT', position: { left: 280, top: 294 } },
  ],
  nodes: [
    // Row 0 — left to right
    { id: 'fetch', label: 'Fetch', icon: '\u21E3', dataType: 'db', stepNumber: '01', position: { left: 112, top: 0 }, ragPhase: 'R' },
    { id: 'retry', label: 'Retry', icon: '\u27F3', dataType: 'db', stepNumber: '02', position: { left: 224, top: 0 }, ragPhase: 'R' },
    { id: 'summarize', label: 'Summarize', icon: '\u03A3', dataType: 'llm', stepNumber: '03', position: { left: 336, top: 0 }, ragPhase: 'A' },
    // Row 1 — right to left (staggered)
    { id: 'match', label: 'Match', icon: '\u25CE', dataType: 'db', stepNumber: '04', position: { left: 280, top: 98 }, ragPhase: 'A' },
    { id: 'posts', label: 'Posts', icon: '\u2B21', dataType: 'llm', stepNumber: '05', position: { left: 168, top: 98 }, ragPhase: 'G' },
    { id: 'verify', label: 'Verify', icon: '\u2727', dataType: 'llm', stepNumber: '06', position: { left: 56, top: 98 }, ragPhase: 'G' },
    // Row 2 — left to right
    { id: 'rescore', label: 'Rescore', icon: '\u21C5', dataType: 'db', stepNumber: '07', position: { left: 0, top: 196 }, ragPhase: 'A' },
    { id: 'dedup', label: 'Dedup', icon: '\u2298', dataType: 'db', stepNumber: '08', position: { left: 112, top: 196 }, ragPhase: 'A' },
    { id: 'screenshots', label: 'Screens', icon: '\u2B1A', dataType: 'db', stepNumber: '09', position: { left: 224, top: 196 }, ragPhase: 'A' },
    { id: 'backfill', label: 'Backfill', icon: '\u21BA', dataType: 'db', stepNumber: '10', position: { left: 336, top: 196 }, ragPhase: 'A' },
  ],
};

// Radar pipeline: News → Identify → Globe (triangle)
// Not a RAG pipeline — single classification step
export const RADAR_LAYOUT: HexLayoutConfig = {
  pipeline: 'radar',
  hiveWidth: 224,
  hiveHeight: 228,
  sourceNode: { id: '_source', label: 'News', icon: '\u25BD', dataType: 'db', stepNumber: 'SRC', position: { left: 0, top: 0 } },
  sinkNodes: [
    { id: '_globe', label: 'Globe', icon: '\u2295', dataType: 'db', stepNumber: 'OUT', position: { left: 56, top: 98 } },
  ],
  nodes: [
    { id: 'identify', label: 'Identify', icon: '\u25C9', dataType: 'llm', stepNumber: '11', position: { left: 112, top: 0 } },
  ],
};

// Article pipeline: Items → Collect → Write → Verify → Polish → Headline → Article
export const ARTICLE_LAYOUT: HexLayoutConfig = {
  pipeline: 'article',
  hiveWidth: 336,
  hiveHeight: 326,
  sourceNode: { id: '_source', label: 'Items', icon: '\u25BD', dataType: 'db', stepNumber: 'SRC', position: { left: 0, top: 0 } },
  sinkNodes: [
    { id: '_article', label: 'Journal', icon: '\u2261', dataType: 'db', stepNumber: 'OUT', position: { left: 224, top: 196 } },
  ],
  nodes: [
    { id: 'collect', label: 'Collect', icon: '\u21E3', dataType: 'db', stepNumber: '01', position: { left: 112, top: 0 }, ragPhase: 'R' },
    { id: 'write', label: 'Write', icon: '\u270E', dataType: 'llm', stepNumber: '02', position: { left: 56, top: 98 }, ragPhase: 'G' },
    { id: 'verify', label: 'Verify', icon: '\u2727', dataType: 'llm', stepNumber: '03', position: { left: 168, top: 98 }, ragPhase: 'G' },
    { id: 'polish', label: 'Polish', icon: '\u25C7', dataType: 'llm', stepNumber: '04', position: { left: 0, top: 196 }, ragPhase: 'G' },
    { id: 'headline', label: 'Headline', icon: 'H', dataType: 'llm', stepNumber: '05', position: { left: 112, top: 196 }, ragPhase: 'G' },
  ],
};

export const LAYOUTS: Record<string, HexLayoutConfig> = {
  news: NEWS_LAYOUT,
  radar: RADAR_LAYOUT,
  article: ARTICLE_LAYOUT,
};
