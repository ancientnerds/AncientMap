# Set Gallery Image as Hero — Design Spec

## Context

Sites display a hero image at the top of the popup, sourced from Wikipedia or the `thumbnail_url` field in the DB. Currently there's no way for founders to pick a better hero image from the gallery. The backend endpoint `POST /api/wiki-images/{site_id}/set-hero` already exists — it downloads the image, converts to WebP, stores on disk, and updates the DB. This feature adds a frontend button to invoke it.

## Design

### Scope

- **Founders only** — button visible only when `user.is_founder === true`
- **Wikimedia images only** — button appears only on images where `sourceType` is `'wikimedia'` or `'wikipedia'` (matches the API's URL whitelist)
- **Location** — bottom caption bar of the `ImageLightbox` component, next to existing attribution info
- **Confirmation** — wait for API response before updating hero (spinner on hero area, no optimistic swap)

### User Flow

1. Founder opens site popup, browses gallery (Photos tab)
2. Clicks a Wikimedia image to open lightbox fullscreen
3. Sees "Set as Hero" button in the caption bar (only on Wikimedia images)
4. Clicks button — button shows loading state ("Setting...")
5. API downloads image to VPS, converts to WebP, updates DB
6. On success: hero image in popup swaps to the new image, button shows brief checkmark
7. On failure: button returns to normal, error shown inline

### Files to Modify

| File | Change |
|------|--------|
| `src/components/ImageLightbox.tsx` | Add `onSetHero` callback prop + "Set as Hero" button in caption bar, gated by `canSetHero` and `isWikimedia` checks |
| `src/components/SitePopup/SitePopup.tsx` | Pass `onSetHero` handler to lightbox, call API with auth token, update `heroImageSrc` on success |
| `src/components/SitePopup/sections/HeroHeader.tsx` | Accept `isSettingHero` prop to show spinner overlay during API call |

### API Contract (existing)

```
POST /api/wiki-images/{site_id}/set-hero
Authorization: Bearer <token>
Content-Type: application/json

{
  "image_url": "https://upload.wikimedia.org/...",
  "attribution_url": "https://commons.wikimedia.org/wiki/File:..."
}

Response: 200 { "thumbnail_url": "/data/images/wiki/{id}/hero.webp" }
```

### Button Behavior

- **Label**: "Set as Hero" with a star icon
- **Loading state**: "Setting..." with spinner, button disabled
- **Success state**: Checkmark icon for 2 seconds, then reverts
- **Error state**: "Failed" in red for 2 seconds, then reverts
- **Visibility**: Only when `canSetHero === true` AND current image `sourceType` includes 'wikimedia' or 'wikipedia'

### Hero Update After Success

1. API returns `{ thumbnail_url: "/data/images/wiki/.../hero.webp" }`
2. SitePopup updates local `heroImageSrc` state to the new URL (with cache-bust query param)
3. HeroHeader re-renders with the new image
4. No page reload needed

### What We Reuse

- `POST /api/wiki-images/{site_id}/set-hero` — existing endpoint, no backend changes
- `useAuth()` hook — existing auth context for `is_founder` check
- `LightboxImage.sourceType` — already tracks image source
- `LightboxImage.sourceUrl` — wikimedia commons page URL for `attribution_url`

## Verification

1. Log in as founder, open a site with Wikimedia photos
2. Click a photo to open lightbox — verify "Set as Hero" button appears in caption
3. Click a non-Wikimedia image — verify button does NOT appear
4. Click "Set as Hero" — verify spinner on hero, then image swaps
5. Log in as non-founder — verify button never appears
6. Check VPS: `public/data/images/wiki/{id}/hero.webp` exists
7. Reload popup — verify hero persists (from DB `thumbnail_url`)
