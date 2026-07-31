# Integrating the user guide

The guide is plain Markdown and uses relative links so it can be rendered by GitHub, a static-site generator, or an in-application Markdown component.

## Directory

```text
docs/user-guide/
├── README.md
├── getting-started.md
├── search-and-filters.md
├── research-tools.md
├── map-layers.md
├── site-records.md
├── offline-and-troubleshooting.md
├── research-notes.md
└── assets/
    └── globe-interface-overview.png
```

## Suggested application routes

| Markdown file | Suggested route |
| --- | --- |
| `README.md` | `/guide` |
| `getting-started.md` | `/guide/getting-started` |
| `search-and-filters.md` | `/guide/search-and-filters` |
| `research-tools.md` | `/guide/research-tools` |
| `map-layers.md` | `/guide/map-layers` |
| `site-records.md` | `/guide/site-records` |
| `offline-and-troubleshooting.md` | `/guide/offline` |
| `research-notes.md` | `/guide/research-notes` |

## Maintenance

Review the guide when any of these components change:

- `src/components/FilterPanel.tsx`
- `src/components/Globe.tsx`
- `src/components/Globe/panels/`
- `src/components/SitePopup/`
- `src/components/DownloadManager.tsx`
- vector, empire, geological, or route configuration

Keep interface labels identical to the application. Where counts or source totals can change, use descriptive language rather than hard-coded values.

