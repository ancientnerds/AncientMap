# AncientMap 3D Scanner: Capture App + Gaussian Splatting Pipeline

> **Status**: Roadmap item (research complete, not yet in development)
> **Date**: 2026-02-20
> **Bittensor verdict**: Not now (<$50K budget vs ~$210K minimum entry). Build as a credit-rewarded feature first; the GPU workload naturally becomes a subnet candidate later if scale justifies it.

---

## The Product

### Mobile Capture App
A cross-platform app (React Native + ViroReact) where users point their phone at an archaeological site, walk around it, and the app shows a real-time coverage heatmap -- red zones mean "film here", green zones mean "captured". When coverage is sufficient, they hit upload.

### Processing Pipeline (Mac Studio M4 Max)
COLMAP (camera poses) -> OpenSplat via Metal (Gaussian splatting) -> SPZ compression. Runs locally on Mac Studio M4 Max. Cost: $0 per model.

### Web Viewer
Spark-based Three.js viewer rendering .spz Gaussian splats in the browser. Opens from the site popup on the globe.

### Value Exchange
Users scan sites for free, get their 3D model back, and earn Lyra credits (100-2000, quality-scaled). AncientMap keeps the model on the platform.

---

## Mobile App

### Best Forkable Candidates

| Project | Platform | License | Stars | Coverage Guidance | Pose Export |
|---|---|---|---|---|---|
| **Brush** | Android + Web | Apache-2.0 | 3,700 | No | Trains splats on-device |
| **RTAB-Map** | iOS + Android | BSD | 3,600 | Partial (loop closure) | Yes |
| **NeRFCapture** | iOS only | MIT | 295 | No | Yes (images + poses) |
| **MultiScan** | iOS + Android | MIT | 148 | No | Yes (images + poses + depth) |

### Key Finding
**No open-source app provides coverage gap visualization.** This is the novel part we need to build. The algorithm is straightforward (camera frustum projection onto a sphere/voxel grid), and ARKit/ARCore provide all required inputs at 60fps.

### Recommended: ViroReact (React Native)
- Cross-platform (iOS ARKit + Android ARCore) from single codebase
- MIT license, 1,700 stars, actively maintained (Morrow-backed, last release Feb 2026)
- React Native ecosystem (web dev friendly)
- Lighter than Unity (no 100MB+ binary bloat)
- Custom native modules bridge to raw ARKit/ARCore pose data

### What We Build on Top
1. **Capture session**: AR camera with real-time tracking
2. **Coverage sphere overlay**: 3D icosphere (500 faces) color-coded red->green based on camera frustum accumulation
3. **Capture logic**: Auto-save frame + 4x4 camera transform matrix at intervals
4. **Export**: ZIP of JPEGs + transforms.json (nerfstudio/InstantNGP compatible format)
5. **Upload**: Send ZIP to AncientMap API

### Coverage Algorithm (the novel part)

Per frame at 60fps:
1. Get camera pose (position + quaternion) from AR session
2. Get camera intrinsics (FoV, resolution)
3. Compute view frustum as a cone
4. Ray-cast frustum onto icosphere faces surrounding the target
5. Increment hit counter per face
6. Color: 0 hits = red, 1-3 = yellow, 4+ = green
7. When >85% of sphere faces are green -> prompt "Ready to upload!"

This is basic 3D geometry, not ML. Runs easily at 60fps on any modern phone.

### Future: Brush Integration
Brush (Rust/WebGPU, Apache-2.0) does on-device Gaussian splatting training -- no server needed. Currently Android + Web only. Once it matures and adds iOS support, could replace the entire server pipeline for previews.

---

## Processing Pipeline (Mac Studio M4 Max)

### Software Stack (installed natively on macOS)
- **FFmpeg** - Frame extraction from video (`brew install ffmpeg`)
- **COLMAP** - Structure-from-Motion (`brew install colmap`)
- **OpenSplat** - Gaussian splatting with Metal backend (build from source with `-DGPU_RUNTIME=MPS`)
- **SPZ converter** - Niantic's SPZ library (Python bindings)
- **trimesh + Pillow** - Quality scoring

### Architecture
```
VPS (existing Docker API)              Mac Studio M4 Max
+-----------------------+              +------------------------+
| FastAPI receives      |  job queue   | Worker process         |
| upload, stores to     |------------>| polls for new jobs     |
| local/R2, creates     |             |                        |
| job record in DB      |             | 1. Download images     |
|                       |  webhook/   | 2. FFmpeg (if video)   |
| Updates DB status     |<-----------| 3. COLMAP (if no       |
| Awards credits        |  callback   |    poses from app)     |
| Serves .spz via CDN   |             | 4. OpenSplat (Metal)   |
+-----------------------+              | 5. SPZ compress        |
                                       | 6. Quality score       |
                                       | 7. Upload .spz to R2   |
                                       | 8. Notify API done     |
                                       +------------------------+
```

### Processing Flow
```
Input (images + optional transforms.json)
  -> [If video] FFmpeg extract frames at 4-10 FPS
  -> [If poses from capture app] Skip COLMAP (saves ~10-15 min!)
  -> [If no poses] COLMAP SfM -> camera poses (~10-20 min on M4 Max)
  -> OpenSplat train 30K iterations via Metal (~30-60 min on M4 Max)
  -> SPZ compress (.ply -> .spz, ~90% smaller)
  -> Quality scoring via trimesh
  -> Upload .spz to R2/CDN
  -> Notify API -> DB update + credit award
```

### Performance Estimates (M4 Max)
- COLMAP SfM (200 images): ~10-20 min
- OpenSplat training (30K iterations, Metal): ~30-60 min
- Total per model: ~40-80 min (or ~30-60 min with app-provided poses)
- Concurrent capacity: 1-2 models simultaneously
- **Cost per model: $0**

---

## Credit Rewards

| Quality Score | Tier | Credits |
|---|---|---|
| 90-100 | Museum quality | 2000 |
| 70-89 | Research quality | 1000 |
| 40-69 | Basic | 500 |
| 0-39 | Rejected | 0 |
| First model for site | Novelty bonus | +500 |

Quality scoring via trimesh (vertex count, watertight, texture resolution, BRISQUE sharpness). Uses existing `CreditGrant` system (`pipeline/database.py:1027`).

---

## Web Viewer

**Spark** (`@sparkjsdev/spark`) - MIT, native Three.js integration, loads .spz directly, mobile-friendly (98%+ WebGL2).

When user clicks a site with a 3D model on the globe -> opens fullscreen viewer with orbit controls.

---

## Files to Create / Modify

### New: Mobile App (separate repo)
```
ancientmap-scanner/
+-- src/
|   +-- screens/
|   |   +-- CaptureScreen.tsx    -- AR camera + coverage sphere
|   |   +-- UploadScreen.tsx     -- Site selection + upload progress
|   |   +-- ResultScreen.tsx     -- View completed model
|   +-- services/
|   |   +-- CoverageTracker.ts   -- Sphere coverage algorithm
|   |   +-- PoseExporter.ts      -- Save frames + transforms.json
|   |   +-- ApiClient.ts         -- Upload to AncientMap API
|   +-- native/
|       +-- ios/CameraPoseBridge.swift    -- Raw ARKit pose extraction
|       +-- android/CameraPoseBridge.kt  -- Raw ARCore pose extraction
```

### New: Processing Worker (runs on Mac Studio)
```
pipeline/splat_worker/
+-- worker.py               -- Job queue poller + orchestration
+-- process.py              -- Full pipeline: FFmpeg -> COLMAP -> OpenSplat -> SPZ
+-- quality.py              -- trimesh-based quality scoring
+-- config.py               -- Paths, API URL, R2 credentials
+-- requirements.txt        -- trimesh, Pillow, brisque, httpx, boto3
```

### New: Backend API
```
api/routes/splats.py        -- Upload endpoint, status polling, viewer data, job queue
api/services/r2_storage.py  -- Cloudflare R2 upload/signed URLs
```

### New: Frontend
```
ancient-nerds-map/src/components/SplatViewer.tsx   -- Spark 3D viewer
```

### Modified
| File | Change |
|---|---|
| `pipeline/database.py` | Add `SplatModel` table |
| `pipeline/lyra/orchestrator.py` | ALTER TABLE migration |
| `ancient-nerds-map/src/components/SitePopup/SitePopup.tsx` | "View 3D" button |
| `ancient-nerds-map/src/styles/index.css` | Viewer styles |
| `api/main.py` | Register splats router |

### Existing Code to Reuse
- `CreditGrant` model (`pipeline/database.py:1027`) -- credit awards
- `DiscordUser.credits` (`pipeline/database.py:985`) -- balance management
- Rate limiter (`api/services/rate_limiter.py`)
- Turnstile CAPTCHA (`api/services/turnstile.py`)
- Discord auth (`api/routes/auth.py`)

---

## Implementation Phases

### Phase 1: Processing Pipeline MVP (Mac Studio)
- Install COLMAP + OpenSplat (Metal) + FFmpeg on Mac Studio
- Test with sample photos of a known site
- Build worker.py job poller + process.py pipeline
- R2 storage for output .spz files
- API endpoint for upload + job queue + status callback
- Quality scoring + credit award

### Phase 2: Web Viewer + Upload Page
- Spark integration in Vite
- SplatViewer component with orbit controls
- Temporary mobile web upload page (fallback for users without the app)
- "View 3D" button in SitePopup
- SplatModel table + status tracking

### Phase 3: Mobile Capture App
- React Native + ViroReact project scaffold
- ARKit/ARCore camera pose extraction (native bridges)
- Coverage sphere algorithm + real-time visualization
- Frame capture + transforms.json export
- Upload flow with progress + site selection
- "How to capture" onboarding tutorial

### Phase 4: Polish + Scale
- Processing failure diagnostics (too few images, blurry, etc.)
- Gallery of community-contributed models
- Notification when model is ready
- Model comparison (replace existing model if new one is better quality)
- Explore Brush for on-device previews
- Bittensor subnet exploration (if scale justifies it)

---

## Key Links

- [OpenSplat](https://github.com/pierotofy/OpenSplat) - Gaussian splatting with Metal support (AGPLv3)
- [Brush](https://github.com/ArthurBrussee/brush) - On-device Gaussian splatting in Rust/WebGPU (Apache-2.0)
- [Spark](https://sparkjs.dev/) - Three.js Gaussian splat renderer (MIT)
- [SPZ format](https://github.com/nianticlabs/spz) - Niantic's compressed splat format (MIT)
- [ViroReact](https://github.com/ReactVision/viro) - React Native AR framework (MIT)
- [COLMAP](https://colmap.github.io/) - Structure-from-Motion
- [RTAB-Map](https://github.com/introlab/rtabmap) - Open-source 3D scanning (BSD)
- [NeRFCapture](https://github.com/jc211/NeRFCapture) - iOS pose capture (MIT)
- [AnySplat](https://github.com/InternRobotics/AnySplat) - Feed-forward 3DGS (skip COLMAP, future)
