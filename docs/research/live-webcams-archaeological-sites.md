# Live Webcams at Archaeological Sites - Research Results

**Date:** 2026-03-09
**Status:** Verified via web search; YouTube video IDs require page inspection

---

## Summary

Most ancient/archaeological sites are covered by **SkylineWebcams** (dominant provider), with the
Western Wall having the most YouTube/direct-embed options. YouTube-specific 24/7 stream video IDs
could not be extracted via web search alone -- YouTube blocks the search crawler. For those, manual
inspection of the embedding pages (aish.com, thekotel.org, tv7israelnews.com, etc.) is needed.

---

## Provider: SkylineWebcams

### Embed Format
SkylineWebcams uses HLS (m3u8) streams. Their embed system works via:
- **Embed domain:** `embed.skylinewebcams.com`
- **Stream URL pattern:** `https://hd-auth.skylinewebcams.com/live.m3u8?a=<token>`
- **Official embed:** Click "Embed" button under live video on their site to get iframe code
- **Restriction:** Only webcam hosts may embed the live video feed; others get a 5-min-refresh photo
- **iframe format (unofficial):**
  ```html
  <iframe src="https://www.skylinewebcams.com/en/webcam/[country]/[region]/[city]/[cam-slug].html"
          width="100%" height="400" frameborder="0" allowfullscreen></iframe>
  ```
  Note: This loads the full page, not just the player. The official embed button provides a cleaner URL.

### Important: Embedding Restrictions
SkylineWebcams restricts embedding to webcam hosts. For third-party use, the recommended approach
is to **link to their page** rather than iframe-embed, unless you have a partnership arrangement.

---

## Site-by-Site Results

### 1. Colosseum, Rome
**Status: CONFIRMED LIVE**
- **SkylineWebcams (primary):**
  - Page: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/colosseo.html
  - Alt: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/roma-colosseo.html
  - View: Colosseum + ruins of Ludus Magnus (gladiator school)
  - Embed type: SkylineWebcams iframe / HLS
- **YouTube 24/7 stream:** NOT FOUND via search. No dedicated YouTube channel identified.
- **Other providers:** iplivecams.com, balticlivecam.com, worldcam.eu (all likely re-embed Skyline)

### 2. Pyramids of Giza, Cairo
**Status: CONFIRMED LIVE**
- **SkylineWebcams (multiple cams):**
  - Great Pyramid: https://www.skylinewebcams.com/en/webcam/egypt/cairo/cairo/great-pyramid-of-giza.html
  - Pyramids + Sphinx: https://www.skylinewebcams.com/en/webcam/egypt/cairo/cairo/pyramids-giza-sphinx.html
  - Third cam: https://www.skylinewebcams.com/en/webcam/egypt/cairo/cairo/le-piramidi-di-giza-il-cairo.html
  - Views from Desert Moon Hotel and Pyramids Loft hotel
  - Embed type: SkylineWebcams iframe / HLS
- **YouTube 24/7 stream:** NOT FOUND via search.
- **Other providers:** webcamtaxi.com, whatsupcams.com

### 3. Acropolis / Parthenon, Athens
**Status: CONFIRMED LIVE (multiple providers)**
- **SkylineWebcams:**
  - Cam 1: https://www.skylinewebcams.com/en/webcam/ellada/atiki/athina/acropolis-athens.html
  - Cam 2: https://www.skylinewebcams.com/en/webcam/ellada/atiki/athina/acropolis.html
  - Embed type: SkylineWebcams iframe / HLS
- **EarthTV:**
  - Page: https://www.earthtv.com/en/webcam/athens-acropolis
  - Camera on COCO-MAT Hotel Athens
  - Embed type: EarthTV player
- **Official acropolis.gr cam:**
  - Page: https://www.acropolis.gr/live-web-camera.php
  - 24/7 sky + monument view
  - Embed type: Likely custom player (needs inspection)
- **Other:** webcameras.gr, whatsupcams.com, windy.com

### 4. Western Wall, Jerusalem
**Status: CONFIRMED LIVE (strongest coverage of all sites)**
- **Aish HaTorah (most well-known):**
  - Page: https://aish.com/western-wall-page/
  - 24/7 live stream, likely YouTube-embedded
  - Embed type: Needs page inspection for YouTube video ID
- **The Kotel / Western Wall Heritage Foundation:**
  - Main: https://thekotel.org/en/western-wall/western-wall-cameras/
  - Prayer Plaza: https://thekotel.org/en/western-wall/cameras-prayer-plaza/
  - Wilson's Arch: https://thekotel.org/en/western-wall/camera-wilsons-arch/
  - Multiple camera angles, always running
  - Embed type: Needs page inspection
- **SkylineWebcams:**
  - Page: https://www.skylinewebcams.com/en/webcam/israel/jerusalem-district/jerusalem/western-wall.html
  - Embed type: SkylineWebcams iframe / HLS
- **EarthCam:**
  - Page: https://www.earthcam.com/world/israel/jerusalem/
  - Powered by Aish HaTorah
  - Embed type: EarthCam player (proprietary)
- **Simcha Hall cam:**
  - Page: https://simchahall.com/en/kotel-camera/
  - Full HD view

### 5. Petra, Jordan (The Treasury)
**Status: CONFIRMED LIVE**
- **SkylineWebcams:**
  - The Treasury: https://www.skylinewebcams.com/en/webcam/jordan/maan/amman/petra-the-treasury.html
  - Visitor Center: https://www.skylinewebcams.com/en/webcam/jordan/maan/amman/petra-visitor-center.html
  - View of Al-Khazneh facade carved into sandstone cliff
  - Embed type: SkylineWebcams iframe / HLS
- **YouTube 24/7:** NOT FOUND

### 6. Pompeii
**Status: NO DIRECT RUINS CAM FOUND**
- No SkylineWebcams camera is pointed at the Pompeii ruins themselves
- **Nearby Vesuvius cams (SkylineWebcams):**
  - Naples-Vesuvius: https://www.skylinewebcams.com/en/webcam/italia/campania/napoli/napoli-vesuvio.html
  - Vesuvius: https://www.skylinewebcams.com/en/webcam/italia/campania/napoli/vesuvio.html
  - Terzigno-Vesuvius: https://www.skylinewebcams.com/en/webcam/italia/campania/napoli/terzigno-vesuvio.html
- **Note:** The Vesuvius webcams show the volcano that buried Pompeii, but not the archaeological site itself.

### 7. Roman Forum, Rome
**Status: NO DEDICATED CAM - use nearby cams**
- No dedicated Roman Forum webcam found on any platform
- **Best alternatives (SkylineWebcams):**
  - Colosseum cam (adjacent): https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/colosseo.html
  - Piazza Venezia (nearby): https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/piazza-venezia.html
  - Rome Skyline (panoramic): https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/roma-skyline.html

### 8. Stonehenge
**Status: CONFIRMED LIVE**
- **English Heritage - Stonehenge Skyscape (official):**
  - Dedicated site: https://stonehengeskyscape.co.uk/
  - Also: https://www.english-heritage.org.uk/visit/places/stonehenge/things-to-do/stone-circle/skyscape/
  - Shows sky above the stones 24/7
  - English Heritage YouTube channel streams solstice events live
  - Embed type: Custom player on stonehengeskyscape.co.uk (needs inspection)
- **Camvista:**
  - Page: https://www.camvista.com/england/other/stonehenge-webcam.php
  - Live streaming with audio

### 9. Machu Picchu
**Status: CONFIRMED LIVE (town view, not ruins directly)**
- **SkylineWebcams:**
  - Aguas Calientes: https://www.skylinewebcams.com/en/webcam/peru/cusco/urubamba/machu-picchu-aguas-calientes.html
  - View of Machupicchu Pueblo (the town), not the ruins from above
  - Embed type: SkylineWebcams iframe / HLS
- **Note:** No webcam was found showing the actual Machu Picchu citadel ruins from above.

### 10. Temple Mount, Jerusalem
**Status: CONFIRMED LIVE**
- **SkylineWebcams:**
  - Page: https://www.skylinewebcams.com/en/webcam/israel/jerusalem-district/jerusalem/temple-mount.html
  - Embed type: SkylineWebcams iframe / HLS
- **TV7 Israel News:**
  - 24/7 live feed: https://www.tv7israelnews.com/jerusalem-live-feed/
  - Shows Old City, Temple Mount, Mount of Olives
  - Embed type: Likely YouTube embed (needs page inspection for video ID)
- **SkylineWebcams (additional Jerusalem cams):**
  - Panorama: https://www.skylinewebcams.com/en/webcam/israel/jerusalem-district/jerusalem/panorama.html
  - Mount of Olives: https://www.skylinewebcams.com/en/webcam/israel/jerusalem-district/jerusalem/mount-of-olives.html

### 11. Largo di Torre Argentina, Rome
**Status: CONFIRMED LIVE**
- **SkylineWebcams:**
  - Page: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/roma-largo-di-torre-argentina.html
  - View of ancient Roman temples + cat sanctuary area
  - Embed type: SkylineWebcams iframe / HLS
- **Official site cam:**
  - Page: https://www.largoargentina.com/Inizio/webcam.htm
  - Embed type: Unknown (needs inspection)

### 12. Trevi Fountain / Piazza Navona, Rome
**Status: CONFIRMED LIVE**
- **Trevi Fountain (SkylineWebcams):**
  - Page: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/fontana-di-trevi.html
  - Added March 2017, operated by Skyline Webcams
  - Embed type: SkylineWebcams iframe / HLS
- **Piazza Navona (SkylineWebcams):**
  - Cam 1: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/piazza-navona-roma.html
  - Cam 2: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/piazza-navona.html
  - View of Fountain of Four Rivers + Church of Sant'Agnese in Agone
  - Site built on Stadium of Domitian (ancient)
  - Embed type: SkylineWebcams iframe / HLS

### 13. Easter Island (Rapa Nui)
**Status: CONFIRMED LIVE**
- **SkylineWebcams:**
  - Page: https://www.skylinewebcams.com/en/webcam/chile/valparaiso/easter-island/easter-island.html
  - View from Te Moai Sunset restaurant towards Ahu Vai Ure and Ahu Ko Te Riku (Moai statues)
  - Embed type: SkylineWebcams iframe / HLS

### 14. Cappadocia, Turkey
**Status: CONFIRMED LIVE**
- **SkylineWebcams:**
  - Page: https://www.skylinewebcams.com/en/webcam/turkey/anatolia-region/nevsehir/cappadocia-uchisar.html
  - View of Pigeon Valley from Helike Hotel, Uchisar
  - Shows fairy chimneys, rock formations, hot air balloons
  - Embed type: SkylineWebcams iframe / HLS

### 15. Angkor Wat, Cambodia
**Status: UNCERTAIN / LOW CONFIDENCE**
- **LiveBeachCam:**
  - Page: https://livebeachcam.net/angkor-wat-live-webcam/
  - Claims to have a live webcam, but reliability unverified
  - Embed type: Unknown
- **No SkylineWebcams coverage** of Angkor Wat
- **No YouTube 24/7 stream found**
- **Note:** This appears to be the weakest coverage of any site on the list.

---

## Recommended Approach for Embedding

### Tier 1: Best embed options (have official/reliable embed paths)
1. **Western Wall** - aish.com, thekotel.org (likely YouTube embeds inside their pages)
2. **Stonehenge** - stonehengeskyscape.co.uk (English Heritage official)
3. **Temple Mount** - tv7israelnews.com (likely YouTube embed)

### Tier 2: SkylineWebcams (reliable streams, embed restrictions apply)
All other sites primarily rely on SkylineWebcams. Options:
- **Link out** to the SkylineWebcams page (simplest, always works)
- **iframe the full page** (works but loads entire Skyline UI, not just player)
- **Extract HLS stream** programmatically using the `hd-auth.skylinewebcams.com/live.m3u8?a=<token>` pattern
  (tokens rotate, so you'd need to re-extract periodically)

### Tier 3: No reliable live stream
- **Pompeii** - Only Vesuvius views, not ruins
- **Roman Forum** - No dedicated cam
- **Angkor Wat** - Unreliable/unverified single source

---

## Next Steps to Get YouTube Video IDs

To extract the actual YouTube video IDs for the Western Wall and Jerusalem streams:
1. Visit https://aish.com/western-wall-page/ and inspect page source for `youtube.com/embed/<VIDEO_ID>`
2. Visit https://thekotel.org/en/western-wall/western-wall-cameras/ and inspect similarly
3. Visit https://www.tv7israelnews.com/jerusalem-live-feed/ and inspect for YouTube embed
4. Visit https://stonehengeskyscape.co.uk/ and check if it uses YouTube or a custom player

These IDs may change over time as live streams restart, so a scraping approach may be needed
for long-term reliability.
