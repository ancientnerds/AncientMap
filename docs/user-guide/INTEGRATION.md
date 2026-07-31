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

> Note: any new extensionless route must be added to `navigateFallbackDenylist` in `ancient-nerds-map/vite.config.ts`, otherwise the installed PWA's service worker serves the cached landing page instead of the route.

## Maintenance

Review the guide when any of these components change:

- `ancient-nerds-map/src/components/FilterPanel.tsx`
- `ancient-nerds-map/src/components/Globe.tsx`
- `ancient-nerds-map/src/components/Globe/panels/`
- `ancient-nerds-map/src/components/SitePopup/`
- `ancient-nerds-map/src/components/DownloadManager.tsx`
- vector, empire, geological, or route configuration

Keep interface labels identical to the application. Where counts or source totals can change, use descriptive language rather than hard-coded values.

