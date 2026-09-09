# Landing page rebuild — research dossier (2026-09-09)

Three parallel research passes feeding the landing page redesign of ancientnerds.com.
Every site claim comes from a page fetched on 2026-09-09 or a cited article; items that
could not be verified are marked **[unverified]**.

Current state (measured 2026-09-09): `index.html` is build-time static HTML, 24 sections,
13,195 px tall, 36 screenshots (4.2 MB in `public/landing/`), 7.3 MB hero video, no canvas,
no iframe, no interactive element. Hero claims "750K+ sites"; `/api/stats` reports
1,759,673 sites (5,004 curated `ancient_nerds`). Stories: 3,189 items from 801 videos across
39 channels. Journals: 23. Public research papers: 24. Country hubs: 98. The globe app's
JS is >2.5 MB (main 532 KB, OrbitControls 350 KB, three core 163 KB, mapboxTheme 1.6 MB)
and loads a 1.89 M-record `sites/index.json` (87 MB gz) — not embeddable as a hero.

---

## Part 1 — What the best landing pages do in 2025/2026

### 1. Live, embedded product previews

**Linear (linear.app, fetched).** The hero is not a screenshot: it embeds working product surfaces (an issue "DRV-8852: Faster app launch" with live activity and agent status like "Worked for 8 sec", a backlog board, a roadmap spanning to Feb 2026, tabbed nav Pulse/Inbox/My issues/Reviews). Toimi's April 2026 teardown calls Linear "the product is the demo" benchmark and notes kinetic word-swapping plus an animated AI agent picking up tasks in the hero ([toimi.pro, 2026-04-21](https://toimi.pro/blog/best-saas-website-designs/)). Userpilot (June 2026) points out proof lives in "the company Linear keeps" (a logo row directly under the hero) rather than testimonials ([userpilot](https://userpilot.com/blog/saas-landing-pages/)). Build: no first-party write-up; the open-source [frontendfyi rebuild](https://github.com/frontendfyi/rebuilding-linear.app) uses Next.js/Tailwind/Framer Motion (a recreation). Mobile degradation: not documented.

**Attio (attio.com, fetched).** Hero "Welcome to agentic revenue", an embedded workflow demo, a Slack demo where "@Attio" is asked "what deals should I focus on today?", and a 5-tab platform walkthrough. Toimi describes a live "Ask Attio" command that executes natural-language queries on the page.

**Framer (framer.com, fetched).** Hero is a design-agent demo with a simulated typed prompt ("Thinking... Created a design plan, 2s"), plus an analytics panel that literally shows Core Web Vitals (LCP 1.1s, INP 95ms, CLS 0.01) and an A/B table where "Home Page 2026" is the winner.

**Resend (resend.com/home, fetched).** A live Node SDK code sample next to a live-rendered React Email preview; SDK tabs for ten languages and framework tabs. The cleanest "tabbed live demo" example found.

**Raycast (raycast.com, fetched).** Hero pairs copy with an interactive QWERTY keyboard visualization mapping benefits to key regions, followed by a tabbed extension showcase.

**Cursor (cursor.com, fetched).** Hero contains an "interactive demo for sighted users" showing Desktop and CLI surfaces (from its accessibility text); the fetched content does not prove the visitor can type into it.

**Stripe (stripe.com, fetched).** Today's hero is a WebGL wave with an explicit static fallback asset (`wave-fallback-desktop.png`), a logo carousel, a stats block and a cycling news feed near the bottom. The 2020 globe write-up is still the canonical build reference: three layered spheres, 60,000 dots cut to ~20,000 by rendering only live countries, antialiasing disabled, animations paused during scroll and throttled, hard 60 fps, "ran on mobile without modification" ([stripe.com/blog/globe](https://stripe.com/blog/globe)).

**GitHub globe (2020).** No textures, ~12,000 five-sided circles. Monitors FPS; below 55.5 fps over the last 50 frames it steps down through four quality tiers: pixel ratio 2.0 to 1.5, fewer PRs drawn, raycast only every 4th frame. Antialiasing off, a halo shader hides the jagged edge ([github.blog](https://github.blog/engineering/engineering-principles/how-we-built-the-github-globe/)).

**Vercel.** Homepage now agent-focused with no live widget evident. The prism hero was rebuilt for the vgpu page and documented on Codrops (2026-09-03): mesh-based refraction, baked textures, and adaptive quality with three signals: low-tier GPU or mobile starts low; laptop under 30% battery and not charging drops low; unstable frame rate drops low ([Codrops](https://tympanus.net/codrops/2026/09/03/from-rays-to-meshes-building-vercels-prism-with-vgpu/)). Vercel's earlier globe was replaced by Shu Ding's COBE: 5 kB, shader-sampled dots from a 256x128 (1 kB) texture, "improved our page performance by almost 60%" versus a three.js SphereGeometry ([shud.in](https://shud.in/thoughts/cobe), Dec 2021).

**Mapbox (fetched).** Hero is copy only; the interactive GL JS gallery sits below the fold. Rotating-globe recipe: autorotate, pause on interaction, slow at high zoom ([docs](https://docs.mapbox.com/mapbox-gl-js/example/globe-spin/)).

**Felt (fetched).** A GIS company puts no live map in its hero: static copy, logos, then a gallery of example maps far down.

**kepler.gl / deck.gl.** Both keep the heavy demo on a separate route rather than the homepage.

**The Pudding.** Scrollytelling via a Svelte `Scrolly` component built on Scrollama (IntersectionObserver, `position: sticky`). Mobile rule: "keep it scrolly, or stack it", keep it short ([pudding.cool/process/responsive-scrollytelling](https://pudding.cool/process/responsive-scrollytelling/)).

**Awwwards 2025.** Site of the Year: Lando Norris (OFF+BRAND). Developer Site of the Year: Messenger, a Three.js + WebSockets planet ([awwwards](https://www.awwwards.com/websites/sites_of_the_year/)). Creative-side ceiling, not a content-site template.

**[unverified]:** Observable (429 on fetch). Figma: no evidence of a live canvas on the homepage. Arc: sunset 2025.

### 2. Structural patterns, and what is dated

- **Bento grids: still default, but evolving.** StudioMeyer's mid-year check (2026-05-17) says bento, dark mode and design systems "held up" ([dev.to](https://dev.to/studiomeyer_io/web-design-trends-2026-what-actually-held-up-after-six-months-23p8)). Bubble (2026-07-30) lists bento as "established" ([bubble.io](https://bubble.io/blog/web-design-trends/)). The 2024 static tile looks dated; 2026 pieces describe the "Active Grid" (hover expands, plays video, reveals data) and single-column stacks on mobile.
- **Scrollytelling / sticky demo panels: established; scroll-jacking is out.** Bubble: scroll-jacking "is slow" and "competes with a browser's ability to respond to a tap" (an INP argument). Always provide nav to skip ahead.
- **Tabbed live demos** (Resend, Raycast, Attio, Stripe code tabs) show breadth without scroll length.
- **Hero with a live widget** (Linear, Attio, Framer, Resend) is the 2026 headline pattern; SaaSFrame frames it as "show don't tell" ([saasframe.io](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples)). LogRocket names the "input-capture hero"; NN/g quotes Perplexity's design head on making the AI input look like a familiar search box with suggested follow-ups ([nngroup](https://www.nngroup.com/articles/perplexity-henry-modisett/)).
- **Proof sections.** A 2,000-page test (Digital Applied, Apr 2026) found "Trusted by 8 of the Fortune 50" beat a logo strip by 14 points. Web Anatomy (Jan 2026): about two-thirds of strong heroes put one dominant proof signal above the fold, not five. Genuine live data (GitHub's real PR arcs, Stripe's stats and news feed) reads as proof.
- **Dated:** static screenshots, abstract 3D shapes, whimsical illustrations, one-size CTAs (SaaSFrame); generic AI imagery and scroll-jacking (Bubble); page-wide kinetic typography; Glassmorphism 2.0 (15–30% frame-rate drops on mid-tier Android, StudioMeyer).

### 3. Motion and interaction: browser status Sept 2026

- **CSS scroll-driven animations** (`animation-timeline: scroll()/view()`): Chrome/Edge 115, Safari 26 (2025-09-15). Firefox still behind a flag in 155 (2026-09-01), Interop 2026 focus area ([web-features explorer](https://web-platform-dx.github.io/web-features-explorer/features/scroll-driven-animations/), [Mozilla Hacks 2026-02-12](https://hacks.mozilla.org/2026/02/launching-interop-2026/)). Gate with `@supports (animation-timeline: scroll())` and `@media (prefers-reduced-motion: no-preference)`; unsupported browsers show the final state with `animation-fill-mode: both`.
- **Scroll-triggered animations** (`animation-trigger`): Chrome 145 only ([Chrome blog](https://developer.chrome.com/blog/scroll-triggered-animations)); IntersectionObserver is the fallback.
- **View Transitions:** same-document Baseline since 2025-10-14 (Firefox 144) ([Chrome blog](https://developer.chrome.com/blog/view-transitions-in-2025)). Cross-document: Chrome 126+, Safari 18.2+, not in Firefox. Fallback is a plain navigation.
- **Reduced motion:** WCAG 2.3.3 plus technique C39. Opt-in pattern (`no-preference`), reduce rather than remove, guarantee visibility when animation is off, mirror in JS via `matchMedia`, explicit pause control for looping canvases (WCAG 2.2.2).

### 4. Performance constraints for interactive heroes

- **Targets:** LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 at p75 field data ([web.dev](https://web.dev/articles/defining-core-web-vitals-thresholds)).
- **Budget:** Alex Russell's 2026 baseline (2025-11-28) is a Galaxy A24 4G on 9 Mbps / 100 ms RTT. For a 3-second load, JS-heavy pages get 1.2 MiB total with 0.62 MiB JS; JS-light 2.0 MiB with 0.3 MiB JS ([infrequently.org](https://infrequently.org/2025/11/performance-inequality-gap-2026/)). Three.js core alone ~600 KB minified; typical 3D heroes exceed 3 MB (Utsubo, 2026-05-20).
- **Recipe:** (1) H1, copy and CTA are real DOM and a static poster is the LCP element; the canvas never is. (2) Load the 3D chunk after `load`/idle; reserve canvas dimensions. (3) Adaptive quality: DPR clamp, FPS watchdog tiers, antialias off. (4) Pause with IntersectionObserver, render-on-demand when idle. (5) OffscreenCanvas + worker for shader compile. (6) On mobile a static WebP is acceptable. (7) Verify with CrUX p75 by device class.

### 5. Authoritative 2025–2026 writeups

- Toimi, "Top 10 Best SaaS Website Designs", 2026-04-21: "no longer show you screenshots — they show you the product working".
- Userpilot, "Interactive Product Demos in 2026", 2026-08-17: Storylane 24.35% vs 3.05% conversion for demo engagers; Navattic analysis of 40,000+ demos; 86% of top demos are HTML/CSS captures; 66% ungated (vendor-adjacent data).
- SaaSFrame, "10 SaaS Landing Page Trends for 2026": immersive product previews, "show don't tell".
- StudioMeyer 2026-05-17; Bubble 2026-07-30; Alex Russell 2025-11-28; Codrops 2026-09-03; Chrome view-transitions 2025-10-08; Chrome scroll-triggered 2025-12-12; WebKit scroll-driven guide 2025-06-20; Mozilla Interop 2026 2026-02-12; Digital Applied Apr 2026; Web Anatomy Jan 2026.

### Top 10 takeaways for ancientnerds (part 1)

1. Hero = real HTML first, globe second. H1, pitch, CTA and a pre-rendered globe poster are the LCP; WebGL fades in after idle.
2. Ship a teaser globe, not the app. COBE-class (5 kB) with pre-aggregated points, "Open the full globe" via `#focus=` deep links. ~0.6 MiB JS on the 3-second critical path.
3. Adaptive quality and pausing are non-negotiable.
4. Stories is the live proof: a real, timestamped feed beats any fake activity widget. One specific number, not a logo wall.
5. Lyra as an input-capture section styled like a search box with 3–4 suggested prompt chips, ungated and rate-limited.
6. Journals and Theo papers as a tabbed live card rendered from real data.
7. One sticky scrollytelling section max, stacked on mobile, skippable. No scroll-jacking.
8. Bento for the product family with "active" tiles, single column on mobile, no glassmorphism blur stacks.
9. Motion as progressive enhancement; visible pause control for the globe.
10. Keep the crawler view intact: every live preview sits on real crawlable HTML (soft-404 lesson), JSON-LD, llms.txt.

---

## Part 2 — Comparable content, science, geo and AI-research sites

### 1. Homepage structures

**Archaeology / ancient-history editorial**
- **Ancient Origins** (fetched via proxy): 6-item "Breaking News" carousel; one large featured card; "Latest" grid; roughly nine topical rails of 3 cards; Premium rail; "Popular"; "Recent Shorts"; recent comments. Card: image, headline, category tag, date, 50–100-word dek. Verdict: a comprehensive index, not a curated front.
- **Archaeology Magazine** (fetched): hero = current issue cover; 5 featured cards (department label + date, headline, dek, photo credit); "Latest News" 8 compact cards; "Trending" 4; "Through the Years" archive picks (2014–2025); "Around the World" 3 expandable location cards. Archive resurfacing is a notable move.

**Place / gazetteer / geo-data**
- **Atlas Obscura** (fetched via proxy): tagline + search box; "Place of the Day" with contributor attribution; destination cards with counts ("Madrid: 160 places, 4 stories"); **"Random Place"** and **"Places Near Me"** buttons; "Been Here? / Want to Visit?" toggles. Their redesign note says Random Place was once demoted to an Easter egg; it is back in the header ([atlasobscura.com](https://www.atlasobscura.com/articles/introducing-atlas-obscuras-new-look)).
- **Pleiades** (fetched): static map illustration, one search box, no counters, no live map.
- **DARE** (imperium.ahlfeldt.se, fetched): the map *is* the landing page; no onboarding, no stats.
- **ArchaeoGLOBE** (fetched): NASA image hero, no map on the homepage.
- **Mapbox Showcase** (fetched): static thumbnails + logo + outcome headline + tags; no live embeds on the listing.
- **Wikidata Query**: no landing, an editor with examples. **Wikimedia Commons**: live counter "147,363,780 freely usable media files", Picture of the Day, per-media-type Upload CTAs.

**Culture / citizen science**
- **Google Arts & Culture** (fetched): stacked horizontal rails, each with a distinct hook (Explore, In Focus, Stories, Today's Fun, AR/3D, games, "Today in History", Recommended with relational labels, Color Discovery, "Cultural 5 Daily").
- **Zooniverse** (via proxy): two live counters (classifications, volunteers), 4 project cards, milestones blog. Caveat: the counters render as **0 without JavaScript** — a crawler sees zeros.

**Data journalism / visual news**
- **The Pudding** (fetched; [repo README](https://github.com/the-pudding/website)): filter row; card = screenshot thumbnail, issue number ("#224"), month/year, short title, one-line dek; "Load More Stories". README: 600x700 image or 600x400 video thumbnails, screenshots act "as a texture" (no legible headline text inside the image), saturated background colour auto-extracted from the image.
- **Reuters Graphics [unverified]** (blocked).
- **The Guardian** (via proxy): hero with 5:4 image, kicker, standfirst; rows of 4–5 cards with ~120px thumbnails, kicker + headline, **no bylines or timestamps on index cards**; "live" badges; "Most viewed" plus "Deeply read". The May 2025 redesign added a masthead carousel and a "My Guardian" follow tab (Design Week; MediaPost 2025-05-08).
- **NYT [desktop unverified]**: June 2025 app revamp keeps the Today feed text-heavy, one swipe from a visual feed with looping video, and a "You" tab that auto-adds a column once read 3–5 times ([WAN-IFRA 2025-06-05](https://wan-ifra.org/2025/06/read-play-swipe-the-strategy-behind-the-new-york-times-app-revamp/)).

**Science journals**
- **Nature** (via proxy): 4-card carousel; card = thumbnail, headline, author, **type label** ("News", "Article Open Access"), date; "Trending" driven by Altmetric badges.
- **Quanta** (fetched): coloured kicker, dek, byline, Save/Read Later; no date or reading time on cards.
- **Aeon** (fetched): content type (essay/video) + category, dek, author, Save, duration only for videos.
- **Science.org [unverified]** (CAPTCHA).

**AI research products**
- **Perplexity** (Discover fetched via proxy): Discover is **open to anonymous visitors**; card = image, headline, summary, "N sources" (4–47 observed), timestamp. Central prompt box, personalised feed, human "curators" programme.
- **Consensus** (fetched): "Research starts here", search box, "220 million papers", Consensus Meter, Study Snapshots. **Elicit** (fetched): hero + product **video** demo, linked example reports. **Semantic Scholar** (fetched): live "237,891,005 papers" inside the search box.

**Newsletter / journal landing pages**
- **Every** (fetched): "Sep 6, 2026 IN Context Window" metadata line, avatar byline. **Ghost Explore**: subscriber counts. **Stratechery**: 2–3-paragraph excerpts per post. **Substack**: "Demystifying the feed" (Oct 2025).

**Dark / terminal / monospace, best-in-class**
- **The Monospace Web** (Oskar Wickström, v0.1.5, 2025-08-20, [owickstrom.github.io](https://owickstrom.github.io/the-monospace-web/)): character-cell grid; tables where only one column may expand; ASCII box-drawing figures; images padded to the grid.
- **Ghostty**: hero is a large ASCII-art ghost, one sentence, two buttons.
- **Warp**: `>_` prompts, headers like `>_[ fig. 1 — the factory ]⌗`, code blocks instead of autoplay video.
- **Claude Code product page**: hero is a terminal-window replay rendered as a static, syntax-highlighted screenshot, not typing animation.
- **U.S. Graphics / Berkeley Mono**: manifesto "dense, not sparse", "expose state and inner workings".
- **Oxide**: terminal-like instance tables on a light background.
- Galleries: Dark Mode Design; Landing.love (Dark Mode 629, Retro 153, ThreeJS 74, full-page video previews); Godly redirects to recent.design; Awwwards has no terminal tag. **Lapa Ninja [unverified]**. Reference: "Terminal CLI Aesthetic" man-page: hierarchy via colour/brightness not size, 80-char measure, honour `prefers-reduced-motion`.

### 2. Feed-style previews

- **Card anatomy:** Perplexity Discover (image / headline / 1-sentence summary / "N sources" / relative time) and Guardian index cards (kicker + headline only) are the two lean extremes. The Pudding adds an issue number and screenshot-as-texture with auto-extracted colour.
- **Density:** Guardian 4–5 per row at 120px thumbs; Ancient Origins rails of 3; Aeon 12–15 cards per scroll depth.
- **Hover/autoplay previews:** YouTube plays a muted 3-second preview on hover. `hover-video-player` handles keyboard focus, touch, bandwidth warnings. `<video autoplay muted>` ignores `prefers-reduced-motion` in all browsers (WHATWG issue 11605), so gate it in JS and offer a toggle.
- **Infinite vs capped:** Baymard/Smashing found "Load more" + lazy-load superior, infinite scroll "downright harmful" for search results and mobile. Every site fetched caps the homepage.
- **Personalisation:** Guardian "My Guardian", NYT "You" tab, Perplexity topic selection, Newsweek "AI Mode" homepage (Digiday).

### 3. Teasing long-form

- **Reading time / length:** Longreads shows word counts; NYT/WSJ "min read"; Quanta and Aeon none. MarTech (Feb 2025) argues for it; readtimer.com warns inaccurate estimates damage trust — use 238 wpm plus per-figure padding.
- **Abstract / excerpt:** Stratechery 2–3 paragraphs; Every and Nature one line; arXiv no inline abstract. No site fetched combines abstract + TOC preview on the homepage — open space.
- **Type labels and badges:** Nature's "Article Open Access", Altmetric "Trending"; Aeon's essay/video label.
- **Citation / evidence signals:** Consensus Meter and Study Snapshots; corpus-size numbers up front.
- **Packaging:** ProPublica (2026-05-05) groups an investigation with methodology, explainers and tip channel, and resurfaces archive investigations; Archaeology Magazine's "Through the Years" does the same cheaply.

### 4. Previewing chat / AI / community safely

- **Live but open:** Perplexity prompt box front and centre; Consensus and Semantic Scholar expose a real search box. Time debuted a homepage AI agent (Digiday 2026-01-22) **[Time.com unverified]**.
- **Replay instead of live:** Elicit uses a video; Claude Code a static terminal replay; Chatmotion replays a scripted conversation with typing simulation; ~80–120 ms per character.
- **Abuse controls:** Netlify — limit at the edge, ~1 request per 2 s per user; Eric Elliott — Turnstile on session creation, `max_tokens` and spend caps are "the only hard guarantees", circuit breaker on spend velocity; canned-prompt pattern: vector-match against pre-approved Q&A before generating.
- **Community counters:** Discord `guilds/{id}/widget.json` returns online count; `with_counts=true` on the invite endpoint gives `approximate_member_count`. Fetch server-side, cache 5–15 min, show total. Zooniverse's JS-only zeros are the anti-pattern.

### 5. Trend pieces 2025–2026

Digiday 2026-01-22 (AI rewrites publisher homepages; Forbes: curated homepages "over"); Nieman Lab / ProPublica 2026-05-05; Guardian redesign May 2025; WAN-IFRA NYT 2025-06-05; Press Gazette 2025-08-07 (Discover is 68% of Google referrals, "ephemeral"); Substack Oct 2025; Squarespace Circle 2025-07-16 ("Archival Index", "Card Play"); Wix 2026-07-20 ("Retro Revival", "Dial-up Design"); Medium 2025-10-21 "The Terminal Aesthetic and the Return of Texture to the Web"; The Monospace Web 2025-08-20.

### What ancientnerds should borrow (part 2)

1. Globe as hero, DARE-style but framed; Atlas Obscura "Random site" + "Near me" on the globe chrome.
2. Live corpus counter inside the search box, rendered server-side (Semantic Scholar, Commons; Zooniverse as anti-pattern).
3. Stories cards = Perplexity Discover anatomy: screenshot, headline, one sentence, "N sources", relative time.
4. Cap the feed at ~8 with "Load more"; no infinite scroll.
5. Screenshot-as-texture thumbnails with auto-extracted accent colour, tinted to the phosphor palette (Pudding).
6. Type labels on every card: STORY / JOURNAL / PAPER, plus Open/Held state (Nature, Aeon).
7. Papers: word count + abstract line + citation-count badge + evidence strip for the citation-integrity gate; abstract + TOC on the front is a differentiator.
8. Package Theo's papers with methodology and sources; resurface archive papers in a "Through the Years" rail (ProPublica, Archaeology Magazine).
9. Lyra preview as a scripted terminal replay with three canned prompts hitting cached answers; free-form only after Turnstile + edge rate limit + spend breaker.
10. Monospace grid discipline, "dense, not sparse", `>_ [ fig. N ]` labels, hierarchy in brightness (Monospace Web, Warp, U.S. Graphics, Ghostty).

---

## Part 3 — Implementation techniques

Verified: the homepage is build-time static `index.html` (hub links baked by the `landingHubs` Vite plugin from `public/data/hubs.snapshot.json`; no React on the page); the globe app loads a 1.89 M-record `sites/index.json`; Lyra chat is login-only SSE (`api/routes/lyra.py`, 15 req/min/IP); Turnstile is used standalone (`api/services/turnstile.py`). Sizes marked "measured" were built locally with esbuild (`--bundle --minify`) and gzip -9.

### 1. Lightweight WebGL globes

| Library | min / gzip | Approach | Many points? | Notes |
|---|---|---|---|---|
| **cobe 2.0.1** | 13.0 kB / **5.9 kB** ([bundlejs](https://deno.bundlejs.com/?q=cobe@2.0.1)) | Single fragment shader; Fibonacci lattice dots masked by a 256×128 land texture ([Shu Ding](https://shud.in/thoughts/cobe)) | `mapSamples` default 16 000, artefacts above ~17 000 ([issue #8](https://github.com/shuding/cobe/issues/8)); v2 moved markers to vertex attributes, no documented ceiling (uncertain) | Zero deps, powers vercel.com; DOM-anchored markers via CSS anchor positioning ([README](https://github.com/shuding/cobe)). **No custom map texture option** — showing site density needs a fork of the shader. Reported ~100% GPU on Windows laptops ([magicui #42](https://github.com/magicuidesign/magicui/issues/42)); mitigate with DPR ≤1.5 and pause off-screen. |
| **three.js 0.182, Points subset** | 501 kB / **126 kB** gz (measured) | `THREE.Points` + `ShaderMaterial`, one draw call | ~1 M points on desktop; ~150 k on older iPhones; `gl_PointSize` capped at 64 px on Apple GPUs | `WebGLRenderer` alone ~100 kB gz. Already what `sitesRenderer.ts` does. |
| **three-globe 2.45.2** | 1.65 MB / **464 kB** (measured) | Wrapper | Hex-bin layer for 10k+ | globe.gl 2.46.2: 1.97 MB / 553 kB. Far too heavy. |
| **deck.gl 9 GlobeView** | core+layer ~147 kB gz | GPU scatterplot, ~1 M points at 60 fps | Yes | GlobeView is **experimental**, no HeatmapLayer. |
| **Mapbox GL v3 globe** | ~400 kB gz + iconset | Tiled vector globe | Via tiles | MapLibre 277 kB gz. Wrong tool for a hero. |

Two decisive facts: (1) A `<canvas>` is **not an LCP candidate** ([web.dev/lcp](https://web.dev/articles/lcp)) — the globe can never help LCP, only hurt via main-thread contention. (2) WebGL in a worker via `OffscreenCanvas` works in Safari 17+.

**Recommendation: cobe**, with two data strategies: (a) cheap — 2 000–5 000 curated markers from a build-time subset (`Int16` lat/lon blob of 5 000 sites ≈ 20 kB); (b) authentic — fork cobe and swap the land mask for a **pre-rendered site-density mask** (equirectangular grayscale WebP, 1–4 kB at 512×256) so the dots *are* the sites. Effort for (b): shader edit plus rebuild, uncertain ~1 day. Never load `sites/index.json` on the landing page.

### 2. Islands / partial hydration in a Vite MPA

No drop-in `client:visible` for plain Vite. Options: `@11ty/is-land` 5.0.1 (1.83 kB, `on:visible | on:idle | on:interaction`, [docs](https://www.11ty.dev/docs/plugins/is-land/)); `react-lazy-hydration` (unmaintained, canonical 40-line trick); or a hand-rolled multi-root boot (recommended — the page has no React root):

```ts
// islands.ts — ~1 kB boot, loaded with <script type="module" defer>
const loaders: Record<string, () => Promise<{ mount: (el: HTMLElement, props: unknown) => void }>> = {
  globe:   () => import('./islands/GlobeIsland'),    // cobe, client-only
  stories: () => import('./islands/StoriesIsland'),  // hydrateRoot over SSR list
  chat:    () => import('./islands/ChatIsland'),
}
const idle = window.requestIdleCallback ?? ((cb: () => void) => setTimeout(cb, 200)) // Safari 26.x still lacks rIC
for (const el of document.querySelectorAll<HTMLElement>('[data-island]')) {
  const run = () => loaders[el.dataset.island!]().then(m => m.mount(el, JSON.parse(el.dataset.props ?? '{}')))
  switch (el.dataset.when) {
    case 'visible': new IntersectionObserver(([e], o) => { if (e.isIntersecting) { o.disconnect(); run() } }, { rootMargin: '200px' }).observe(el); break
    case 'interaction': el.addEventListener('pointerenter', run, { once: true, passive: true }); el.addEventListener('focusin', run, { once: true }); break
    default: idle(run)
  }
}
```

Each island's `mount` calls `hydrateRoot` when the SSR markup is React-rendered (via the sidecar's `renderToString`), or `createRoot` when the server output is a static placeholder (globe, chat).

Pitfalls: hydration mismatch (React 18 recovers from some; `suppressHydrationWarning` one level deep; `useEffect → setIsClient(true)` for client-only content; SSR props serialised into `data-props` and reused unchanged, fetch fresher data only *after* hydration); CLS (reserve island boxes with `aspect-ratio`/`min-height`, `font-display: optional`); `requestIdleCallback` still flagged in Safari 26.x — always polyfill; freshness (`hubs.snapshot.json` is read at build time → SSR'd cards are as fresh as the last deploy; either refresh client-side after hydrate or route `/` through the SSR sidecar with a short cache).

### 3. Live feed previews

- Scroll-snap carousel universally supported; Chrome 135+ adds `::scroll-button()` / `::scroll-marker` (Chromium-only), guard with `@supports selector(::scroll-button(right))` ([Chrome blog](https://developer.chrome.com/blog/carousels-with-css)).
- `animation-timeline: scroll()` ~82.6% global; author the end state first, wrap in `@supports`.
- A pure-CSS marquee is fine for a headline strip only if ≤5 s or with a stop button (WCAG 2.2.2).
- APG carousel: rotation control is the first focusable element; pause on hover **and** focus, no auto-resume; `aria-live` off while rotating. Simplest compliant design: **no auto-advance by default**; `prefers-reduced-motion: reduce` disables it entirely.
- SEO: render 6–8 story cards, latest journals and the paper list as plain `<a href>` in the SSR HTML (extend `hubs.snapshot.json` with `stories[]` and `journals[]`; the exporter/publish hooks already rewrite it). Screenshots `<img loading="lazy" width height>`; `fetchpriority="high"` only above the fold.

### 4. Embedding a working AI chat demo safely

Threat model: public LLM endpoints get used as free proxies ("denial of wallet"). Consensus hardening: Turnstile on **session creation**, per-IP and global rate limits, input length cap, `max_tokens` cap, cheap model, narrow system prompt, spend circuit breaker.

Turnstile mechanics ([Cloudflare docs](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)): tokens valid 300 s, single use, send `remoteip`. Verify once, then issue a short-lived session. Pre-clearance needs the zone behind Cloudflare's WAF — likely not applicable here.

Concrete design for this codebase:
1. `POST /api/v1/lyra/demo/session`: `verify_turnstile(token, ip)` (existing) → HMAC-signed session `{exp: +10 min, msgs: 5}`; `RateLimiter(max_requests=3, window_seconds=86400, namespace="lyra_demo_session")` per IP (existing Redis-first limiter).
2. `POST /api/v1/lyra/demo/chat`: session required; input ≤300 chars, ≤4 turns, `max_tokens` ≤300, fixed narrow system prompt; **global daily cap** that flips the endpoint to replay mode (the MiniMax 5-hour token window is shared with Theo).
3. Client: reuse the SSE `getReader()` loop from `LyraChatModal.tsx`; suggested-prompt chips.
4. Replay fallback: 3–4 recorded conversations as static JSON played through the same renderer with a timed chunk stream; default state before "Try it live", and the state when Turnstile fails, budget is exhausted, or JS is off (transcript SSR'd as text).

### 5. Measuring and enforcing a budget in CI

| Tool | Use |
|---|---|
| **size-limit + @size-limit/file** 13.0.3 | Brotli by default, globs on `dist/assets/landing-*.js`; fails the PR. Add to `lint-frontend` after `npm run build`. |
| **Lighthouse CI** (@lhci/cli 0.15.1, treosh/lighthouse-ci-action@v12) | `staticDistDir: ./dist` or `vite preview`; mobile default; `numberOfRuns: 3–5`. Assertions: LCP ≤2500, CLS ≤0.1, TBT ≤200, `total-byte-weight`; `budget.json` resource sizes. |
| **Lighthouse user flows** 13.4.1 | `startTimespan()` around "click suggested prompt / scroll carousel" gives a real INP number in CI. |
| **Playwright** | Hydration-error and console-error gates, not numbers. |
| **web-vitals** 6.2.1 | ~3 kB brotli RUM; only field data decides CrUX. |

Budgets (Google thresholds unchanged; internal alerts at 80%: 2.0 s / 160 ms / 0.08). Suggested for this page (not a standard): initial critical JS ≤30 kB br, all islands after idle ≤150 kB br (react-dom ≈40 kB br, cobe 6 kB, chat/stories UI ≈30 kB), hero poster ≤80 kB, total page weight before interaction ≤600 kB. Calibrate LHCI on the CI runner.

### Recommended architecture (part 3)

Keep the static Vite-built `index.html` with inlined critical CSS, poster-image LCP and baked hub links. Add an islands layer instead of a page-level React root.

1. **Hero** — headline + poster `<img fetchpriority="high">` (LCP) with `#focus=` deep link into `/globe.html`. **GlobeIsland** (`data-when="idle"`, cobe 6 kB, vanilla mount): DPR ≤1.5, markers from a 5 000-site blob, later a forked density mask. Pauses on `visibilitychange` and when scrolled out; renders nothing under `prefers-reduced-motion` or `saveData` (poster stays).
2. **StoriesIsland** (`data-when="visible"`) — SSR'd 8 cards with screenshots and real links; CSS scroll-snap + `::scroll-button` enhancement; `hydrateRoot` only to add APG-compliant controls and client-side refresh. No auto-rotation by default.
3. **Journals / Papers** — pure SSR grids, zero JS; papers reuse the existing `paperLinksHtml`.
4. **ChatIsland** (`data-when="visible"`) — replay mode from static transcripts (also SSR'd as text); "Try it live" → invisible Turnstile → demo session → SSE. Server: session limiter, 5 msgs/10 min, 300-token cap, global daily circuit breaker.
5. **islands.ts** boot (≈1 kB, `defer`), `requestIdleCallback` polyfilled; every island box has `aspect-ratio`/`min-height` reserved.

Chunking: `manualChunks` for `react-dom` shared by stories+chat; cobe in its own chunk; nothing from `three` on this page.

CI gates: `size-limit` on `landing-*.js`, LHCI mobile assertions (3 runs), one Lighthouse timespan flow for INP, Playwright zero-hydration-error check. RUM via `web-vitals` to confirm in CrUX.

Uncertain items: cobe marker ceiling in v2, effort of the density-mask fork, whether the site is proxied through Cloudflare (affects pre-clearance only).
