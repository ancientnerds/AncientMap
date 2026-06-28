# Set Gallery Image as Hero — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let founders set any Wikimedia gallery image as the site's hero image via a button in the lightbox caption bar.

**Architecture:** Add `onSetHero` callback prop to `ImageLightbox`. SitePopup passes a handler that calls `POST /api/wiki-images/{site_id}/set-hero` with the image URL and attribution. On success, update the local `heroImageSrc` state. No backend changes needed.

**Tech Stack:** React, existing FastAPI endpoint, existing auth token from localStorage

---

### Task 1: Add `onSetHero` prop and button to ImageLightbox

**Files:**
- Modify: `ancient-nerds-map/src/components/ImageLightbox.tsx`

- [ ] **Step 1: Add new props to ImageLightboxProps interface**

In `ImageLightbox.tsx:27-32`, add the new props:

```typescript
interface ImageLightboxProps {
  images: LightboxImage[]
  currentIndex: number
  onClose: () => void
  onNavigate: (index: number) => void
  onSetHero?: (image: LightboxImage) => Promise<boolean>  // returns true on success
}
```

- [ ] **Step 2: Add state and destructure new prop**

Inside the component function (after line 39), add the prop and state:

```typescript
export default function ImageLightbox({
  images,
  currentIndex,
  onClose,
  onNavigate,
  onSetHero,
}: ImageLightboxProps) {
```

Add state after the existing `containerSize` state (after line 48):

```typescript
  const [heroState, setHeroState] = useState<'idle' | 'setting' | 'success' | 'failed'>('idle')
```

Reset heroState when navigating (add to the existing reset effect at line 60):

```typescript
  setHeroState('idle')
```

- [ ] **Step 3: Add the click handler**

Add after the existing `handleClose` function:

```typescript
  const handleSetHero = async () => {
    if (!onSetHero || heroState === 'setting') return
    setHeroState('setting')
    const ok = await onSetHero(current)
    setHeroState(ok ? 'success' : 'failed')
    setTimeout(() => setHeroState('idle'), 2000)
  }
```

- [ ] **Step 4: Add the button in the caption bar**

In the `lightbox-attribution` div (after line 420, before the closing `</div>` of `lightbox-attribution`), add:

```tsx
            {onSetHero && current.sourceType === 'wikimedia' && (
              <button
                className="lightbox-set-hero"
                onClick={handleSetHero}
                disabled={heroState === 'setting'}
              >
                {heroState === 'setting' ? (
                  <>
                    <div className="map-loading-spinner" style={{ width: 12, height: 12 }} />
                    Setting...
                  </>
                ) : heroState === 'success' ? (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Done
                  </>
                ) : heroState === 'failed' ? (
                  <>Failed</>
                ) : (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                    </svg>
                    Set as Hero
                  </>
                )}
              </button>
            )}
```

- [ ] **Step 5: Add CSS for the button**

In `ancient-nerds-map/src/styles/index.css`, find the existing `.lightbox-source-link` styles and add after them:

```css
.lightbox-set-hero {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--nerv-o, #FF9830);
  background: none;
  border: 1px solid rgba(255, 152, 48, 0.3);
  padding: 3px 10px;
  margin-left: 8px;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.lightbox-set-hero:hover:not(:disabled) {
  border-color: rgba(255, 152, 48, 0.6);
  background: rgba(255, 152, 48, 0.06);
  color: #ffb060;
}

.lightbox-set-hero:disabled {
  opacity: 0.6;
}
```

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean, no errors

- [ ] **Step 7: Commit**

```bash
git add ancient-nerds-map/src/components/ImageLightbox.tsx ancient-nerds-map/src/styles/index.css
git commit -m "feat: add Set as Hero button to lightbox for Wikimedia images"
```

---

### Task 2: Wire up the handler in SitePopup

**Files:**
- Modify: `ancient-nerds-map/src/components/SitePopup/SitePopup.tsx`

- [ ] **Step 1: Add hero-setting state**

After the existing `lightboxItems` state (line 303), add:

```typescript
  const [isSettingHero, setIsSettingHero] = useState(false)
```

- [ ] **Step 2: Create the handleSetHero callback**

Add after `handleItemClick` (after line 439):

```typescript
  const handleSetHero = useCallback(async (image: LightboxImage): Promise<boolean> => {
    if (!authToken || !isFounder || !displaySite.id) return false
    setIsSettingHero(true)
    try {
      const res = await fetch(`${config.api.baseUrl}/wiki-images/${displaySite.id}/set-hero`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_url: image.src,
          attribution_url: image.sourceUrl || '',
        }),
      })
      if (!res.ok) return false
      const data = await res.json()
      if (data.thumbnail_url) {
        galleryHook.setHeroImageSrc?.(data.thumbnail_url + '?t=' + Date.now())
      }
      return true
    } catch {
      return false
    } finally {
      setIsSettingHero(false)
    }
  }, [authToken, isFounder, displaySite.id])
```

Note: `LightboxImage` is already imported on line 63.

- [ ] **Step 3: Pass onSetHero to ImageLightbox**

Find the lightbox rendering (line 885) and add the prop:

```tsx
    <ImageLightbox
      images={lightboxItems}
      currentIndex={lightboxIndex}
      onClose={() => setLightboxIndex(null)}
      onNavigate={setLightboxIndex}
      onSetHero={isFounder ? handleSetHero : undefined}
    />,
```

- [ ] **Step 4: Add setHeroImageSrc to the gallery hook return**

In `ancient-nerds-map/src/components/SitePopup/gallery/useGalleryData.ts`, expose a setter for `heroImageSrc`:

Add state for override (after the existing `wikiImages` state, around line 37):

```typescript
  const [heroImageOverride, setHeroImageOverride] = useState<string | null>(null)
```

Update the `heroImageSrc` computation (around line 141):

```typescript
  const heroImageSrc = heroImageOverride || thumbnailUrl || wikiHero?.full || photoItems[0]?.full
```

Add to the return object:

```typescript
  setHeroImageSrc: setHeroImageOverride,
```

Also add to `GalleryHookReturn` in `galleryTypes.ts`:

```typescript
  setHeroImageSrc: ((src: string) => void) | undefined
```

And to `useEmpireGalleryData.ts` return:

```typescript
  setHeroImageSrc: undefined,
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean, no errors

- [ ] **Step 6: Commit**

```bash
git add ancient-nerds-map/src/components/SitePopup/SitePopup.tsx \
       ancient-nerds-map/src/components/SitePopup/gallery/useGalleryData.ts \
       ancient-nerds-map/src/components/SitePopup/gallery/galleryTypes.ts \
       ancient-nerds-map/src/components/SitePopup/gallery/useEmpireGalleryData.ts
git commit -m "feat: wire Set as Hero handler through SitePopup to API"
```

---

### Task 3: Add loading spinner overlay on HeroHeader

**Files:**
- Modify: `ancient-nerds-map/src/components/SitePopup/sections/HeroHeader.tsx`
- Modify: `ancient-nerds-map/src/components/SitePopup/SitePopup.tsx`

- [ ] **Step 1: Add isSettingHero prop to HeroHeader**

In `HeroHeaderProps` (in `types.ts`), add:

```typescript
  isSettingHero?: boolean
```

- [ ] **Step 2: Add spinner overlay in HeroHeader**

In `HeroHeader.tsx`, destructure the new prop and add a spinner overlay after the `LazyImage` (around line 177):

```tsx
      {isSettingHero && (
        <div className="popup-hero-loading" style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div className="map-loading-spinner" />
        </div>
      )}
```

- [ ] **Step 3: Pass isSettingHero from SitePopup**

Find where `<HeroHeader` is rendered in `SitePopup.tsx` and add the prop:

```tsx
  isSettingHero={isSettingHero}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean, no errors

- [ ] **Step 5: Commit and push**

```bash
git add ancient-nerds-map/src/components/SitePopup/sections/HeroHeader.tsx \
       ancient-nerds-map/src/components/SitePopup/SitePopup.tsx \
       ancient-nerds-map/src/components/SitePopup/types.ts
git commit -m "feat: show loading spinner on hero while setting new image"
git push origin main
```

---

### Task 4: Verify end-to-end

- [ ] **Step 1: TypeScript full check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: Clean

- [ ] **Step 2: Watch CI**

Run: `gh run watch <id> --exit-status`
Expected: All green, deployed

- [ ] **Step 3: Manual verification checklist**

1. Open site popup for a site with Wikimedia photos (e.g., Gobekli Tepe)
2. Click a Wikimedia photo to open lightbox
3. Verify "Set as Hero" button appears in caption bar (orange, star icon)
4. Click a non-Wikimedia image — verify button does NOT appear
5. Not logged in — verify button does NOT appear
6. Click "Set as Hero" — verify hero shows spinner, then swaps to new image
