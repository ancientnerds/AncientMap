# Stories Tab in Site Popup — Design Spec

## Context

Stories (extracted from YouTube archaeology videos) already link to sites via `site_id` FK in the database. The API supports filtering stories by site (`/news/feed?site_id=<uuid>`). But there's no way to see related stories when viewing a site popup on the globe. This feature adds a "Stories" tab to the site popup gallery, showing news cards for that site.

## Design

### Approach

Add `'stories'` to the existing gallery tab system. The Stories tab is special — it doesn't use `UnifiedGalleryItem` like other tabs. Instead it fetches `NewsItemData[]` from the API and renders `NewsCard` components directly in a scrollable list (same pattern as the books/papers text list, but using the existing news card component).

### Data Flow

1. `useGalleryData` hook gets a new `storiesItems: NewsItemData[]` array and `isLoadingStories: boolean`
2. On mount, fetch `/news/feed?site_id={siteId}&page_size=20&sort=significance` 
3. `GalleryTabs` receives `storyCount` and `isLoadingStories` props, renders a new "Stories" tab button
4. `GalleryContent` checks `activeTab === 'stories'` and renders `NewsCard` components in a vertical list
5. The stories tab does NOT participate in the `currentItems` / `UnifiedGalleryItem` system — it has its own render path (like webcams)

### Files to Modify

| File | Change |
|------|--------|
| `components/SitePopup/types.ts` | Add `'stories'` to `GalleryTab` union, add `storyCount` + `isLoadingStories` to `GalleryTabsProps` |
| `components/SitePopup/gallery/useGalleryData.ts` | Add stories fetch logic, return `storiesItems` + `isLoadingStories` |
| `components/SitePopup/gallery/galleryTypes.ts` | Add `storiesItems` + `isLoadingStories` to `GalleryHookReturn` |
| `components/SitePopup/gallery/GalleryTabs.tsx` | Add Stories tab config with newspaper icon |
| `components/SitePopup/gallery/GalleryContent.tsx` | Add stories render branch using NewsCard |
| `components/SitePopup/SitePopup.tsx` | Pass `storyCount` and `isLoadingStories` to GalleryTabs |

### UI Details

- Tab label: "Stories"
- Tab icon: newspaper/article SVG
- Tab position: after Myths (last content tab, before any future tabs)
- Card display: vertical list of `NewsCard` components with `size="sm"`, matching the sidebar panel's compact style
- Empty state: "No stories found for this site"
- Offline state: "Stories require internet"

### What We Reuse

- `NewsCard` component as-is (handles expand/collapse, thumbnails, significance, etc.)
- `/news/feed` API endpoint with `site_id` filter
- Existing gallery tab infrastructure (tabs, loading states, empty states)
- Existing `news-cards.css` styles (`.news-feed-item` inside the popup)

## Verification

1. Open a site popup for a site that has linked news stories (e.g., Gobekli Tepe)
2. Verify the Stories tab appears with correct count
3. Click the tab — stories render as compact news cards
4. Verify expand/collapse works on individual cards
5. Open a site with no stories — verify empty state shows
6. TypeScript compiles cleanly
