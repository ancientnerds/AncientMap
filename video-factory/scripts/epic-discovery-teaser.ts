/**
 * Epic Discovery Teaser - Production Script
 *
 * Option A: Dramatic style, video only (no voiceover/music)
 * Tagline: "Modern Tech for Ancient Mysteries"
 * Featured Site: Machu Picchu
 */

export const SCRIPT = {
  title: 'ANCIENT NERDS',
  tagline: 'Modern Tech for Ancient Mysteries',
  duration: 60, // seconds
  fps: 30,

  // Shot list with timing (in seconds)
  shots: [
    {
      id: 'intro-logo',
      start: 0,
      end: 3,
      type: 'logo-reveal',
      text: 'ANCIENT NERDS',
      animation: 'fade-in-glow',
    },
    {
      id: 'intro-tagline',
      start: 3,
      end: 5,
      type: 'tagline',
      text: 'Modern Tech for Ancient Mysteries',
      animation: 'fade-in-up',
    },
    {
      id: 'globe-reveal',
      start: 5,
      end: 10,
      type: 'globe-spin',
      text: '800,000+ Sites',
      action: 'markers-cascade',
      animation: 'scale-in',
    },
    {
      id: 'site-giza',
      start: 10,
      end: 14,
      type: 'fly-to',
      site: 'Pyramids of Giza',
      location: 'Egypt',
      coords: { lat: 29.9792, lon: 31.1342 },
    },
    {
      id: 'site-machu-picchu',
      start: 14,
      end: 18,
      type: 'fly-to',
      site: 'Machu Picchu',
      location: 'Peru',
      coords: { lat: -13.1631, lon: -72.5450 },
      featured: true,
    },
    {
      id: 'site-stonehenge',
      start: 18,
      end: 22,
      type: 'fly-to',
      site: 'Stonehenge',
      location: 'England',
      coords: { lat: 51.1789, lon: -1.8262 },
    },
    {
      id: 'feature-filter',
      start: 22,
      end: 28,
      type: 'feature-demo',
      text: 'Filter by Type',
      action: 'filter-panel-demo',
    },
    {
      id: 'feature-search',
      start: 28,
      end: 34,
      type: 'feature-demo',
      text: 'Search Any Site',
      action: 'search-typing',
      searchQuery: 'Temple',
    },
    {
      id: 'feature-popup',
      start: 34,
      end: 40,
      type: 'popup-demo',
      text: 'Rich Details & Images',
      site: 'Machu Picchu',
      action: 'popup-open',
    },
    {
      id: 'stats',
      start: 40,
      end: 48,
      type: 'stats-counter',
      stats: [
        { value: '800,000+', label: 'Sites' },
        { value: '50+', label: 'Categories' },
        { value: '200+', label: 'Countries' },
      ],
      animation: 'count-up',
    },
    {
      id: 'explore',
      start: 48,
      end: 55,
      type: 'globe-breathe',
      text: 'Explore History',
      animation: 'pulse-glow',
    },
    {
      id: 'outro',
      start: 55,
      end: 60,
      type: 'cta',
      text: 'ancientnerds.com',
      animation: 'glow-pulse',
    },
  ],

  // Featured sites for the teaser
  featuredSites: [
    {
      name: 'Pyramids of Giza',
      location: 'Egypt',
      lat: 29.9792,
      lon: 31.1342,
      type: 'Pyramid complex',
      period: '2560 BC',
    },
    {
      name: 'Machu Picchu',
      location: 'Peru',
      lat: -13.1631,
      lon: -72.5450,
      type: 'City/town/settlement',
      period: '15th Century',
      featured: true,
    },
    {
      name: 'Stonehenge',
      location: 'England',
      lat: 51.1789,
      lon: -1.8262,
      type: 'Stone circle',
      period: '3000 BC',
    },
  ],

  // Stats to display
  stats: {
    totalSites: 800000,
    categories: 50,
    countries: 200,
  },

  // Visual settings
  visuals: {
    backgroundColor: '#000000',
    accentColor: '#00b4b4',  // Teal
    brandColor: '#c02023',   // Red
    goldColor: '#FFD700',
  },
};

export default SCRIPT;
