/**
 * Shared disclaimer HTML content used by both:
 * - DisclaimerModal.tsx (React, globe view)
 * - landing page (vanilla JS popup)
 *
 * Uses <details>/<summary> for native accordion behavior.
 * The CSS classes match the existing disclaimer styles in index.css.
 */

export function getDisclaimerHTML(buildHash?: string, buildTime?: string): string {
  const footerHTML = buildHash && buildTime
    ? `<div class="disclaimer-footer"><p>
        <a href="https://github.com/AncientNerds/AncientMap/commit/${buildHash}"
           target="_blank" rel="noopener noreferrer"
           style="font-family:monospace;color:inherit;text-decoration:none;opacity:0.7">v1.0.0-${buildHash}</a>
        &middot; Built ${new Date(buildTime).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
      </p></div>`
    : ''

  return `
<h2>Disclaimer &amp; Legal</h2>

<div class="disclaimer-preamble">
  <p>ANCIENT NERDS exists because of the extraordinary work of communities and researchers
  who have spent decades documenting the world&rsquo;s ancient sites &mdash; often voluntarily,
  often without recognition.</p>
  <p>We are not here to replace any of them. ANCIENT NERDS is the entry point &mdash;
  the databases listed below are where the real depth lives. Every dot on our map
  links back to its source, because we want you to find <em>them</em>.</p>
  <p><strong>We stand on the shoulders of giants.</strong></p>
</div>

<details class="disclaimer-section" open>
  <summary class="disclaimer-section-header">
    <span>Data Sources &amp; Attribution</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <p>This platform aggregates archaeological and historical site data from multiple open-source databases. Each source maintains its own licensing terms:</p>
    <div class="source-licenses">
      <div class="license-group">
        <h4>Creative Commons Attribution (CC BY)</h4>
        <ul>
          <li><strong>CC BY 4.0:</strong> <a href="https://eamena.org/" target="_blank" rel="noopener noreferrer">EAMENA</a>, <a href="https://opencontext.org/" target="_blank" rel="noopener noreferrer">Open Context</a>, <a href="https://www.geonames.org/" target="_blank" rel="noopener noreferrer">GeoNames</a>, <a href="https://volcano.si.edu/" target="_blank" rel="noopener noreferrer">HolVol Volcanic</a>, <a href="https://zenodo.org/records/10473706" target="_blank" rel="noopener noreferrer">LIST Latin Inscriptions</a>, <a href="https://zenodo.org/records/17128262" target="_blank" rel="noopener noreferrer">Luwian Studies Atlas</a>, <a href="https://www.archaeology.ie/" target="_blank" rel="noopener noreferrer">Ireland NMS</a>, <a href="https://github.com/Vperipato/ade2541" target="_blank" rel="noopener noreferrer">Pre-Columbian Amazon</a> (Peripato et al. 2023)</li>
          <li><strong>CC BY 3.0:</strong> <a href="https://pleiades.stoa.org/" target="_blank" rel="noopener noreferrer">Pleiades</a>, <a href="http://nomisma.org/" target="_blank" rel="noopener noreferrer">Nomisma Coins</a></li>
          <li><strong>CC BY:</strong> <a href="https://github.com/Seshat-Global-History-Databank/cliopatria" target="_blank" rel="noopener noreferrer">Cliopatria Dataset</a> (empire boundaries, Nature Scientific Data)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Creative Commons Attribution-ShareAlike (CC BY-SA)</h4>
        <ul>
          <li><strong>CC BY-SA 4.0:</strong> <a href="https://ancientnerds.com" target="_blank" rel="noopener noreferrer">Ancient Nerds (Original)</a> (includes curated Rock Art sites), <a href="https://www.helladic.info/" target="_blank" rel="noopener noreferrer">Mycenaean Atlas</a>, <a href="https://www.roceeh.uni-tuebingen.de/roadweb/" target="_blank" rel="noopener noreferrer">ROCEEH ROAD</a></li>
          <li><strong>CC BY-SA 3.0:</strong> <a href="https://imperium.ahlfeldt.se/" target="_blank" rel="noopener noreferrer">DARE</a>, <a href="https://vici.org/" target="_blank" rel="noopener noreferrer">Vici.org</a></li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Creative Commons NonCommercial</h4>
        <ul>
          <li><strong>CC BY-NC-SA 4.0:</strong> <a href="https://topostext.org/" target="_blank" rel="noopener noreferrer">ToposText</a>, <a href="https://seshat-db.com/" target="_blank" rel="noopener noreferrer">Seshat Global History Databank</a> (historical polity data &amp; social complexity variables)</li>
          <li><strong>CC BY-NC-SA 3.0:</strong> <a href="https://www.davidrumsey.com/" target="_blank" rel="noopener noreferrer">David Rumsey Maps</a></li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Public Domain &amp; Open Government Data</h4>
        <ul>
          <li><strong>CC0 / Public Domain:</strong> <a href="https://www.wikidata.org/" target="_blank" rel="noopener noreferrer">Wikidata</a>, <a href="https://www.metmuseum.org/" target="_blank" rel="noopener noreferrer">Metropolitan Museum of Art</a>, <a href="https://www.si.edu/openaccess" target="_blank" rel="noopener noreferrer">Smithsonian Open Access</a>, <a href="https://openlibrary.org/" target="_blank" rel="noopener noreferrer">Open Library</a> (book covers)</li>
          <li><strong>US Government Public Domain:</strong> <a href="https://www.ncei.noaa.gov/maps/hazards/" target="_blank" rel="noopener noreferrer">NCEI Natural Hazards</a> (earthquakes, tsunamis, volcanoes)</li>
          <li><strong>Open Government Licence:</strong> <a href="https://historicengland.org.uk/" target="_blank" rel="noopener noreferrer">Historic England</a>, <a href="https://canmore.org.uk/" target="_blank" rel="noopener noreferrer">Canmore Scotland</a>, <a href="https://coflein.gov.uk/" target="_blank" rel="noopener noreferrer">Coflein Wales</a></li>
          <li><strong>ODbL:</strong> <a href="https://www.openstreetmap.org/" target="_blank" rel="noopener noreferrer">OpenStreetMap Historic</a></li>
          <li><strong>CC0 (metadata):</strong> <a href="https://www.europeana.eu/" target="_blank" rel="noopener noreferrer">Europeana</a> (item licenses vary)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>UNESCO World Heritage</h4>
        <p>World Heritage Site locations and names are factual data used with attribution. Copyright &copy; 1992&ndash;2026 <a href="https://whc.unesco.org/" target="_blank" rel="noopener noreferrer">UNESCO/World Heritage Centre</a>. All rights reserved. Each site links back to its UNESCO page.</p>
      </div>
      <div class="license-group">
        <h4>Academic &amp; Research Use</h4>
        <ul>
          <li><a href="https://oxrep.classics.ox.ac.uk/databases/shipwrecks_database/" target="_blank" rel="noopener noreferrer">OXREP Shipwrecks</a> (cite Strauss 2013)</li>
          <li><a href="http://www.passc.net/EarthImpactDatabase/" target="_blank" rel="noopener noreferrer">Earth Impact Database</a> (non-commercial research &amp; education)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Site Images (Self-Hosted)</h4>
        <p>Archaeological site images are sourced from <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener noreferrer">Wikipedia and Wikimedia Commons</a> under their respective Creative Commons licenses (CC BY-SA 4.0, CC BY 4.0, CC0, Public Domain). Individual image attribution &mdash; including photographer, license, and source &mdash; is displayed when viewing each image. All images link back to their original Wikimedia Commons page.</p>
      </div>
      <div class="license-group">
        <h4>Wikipedia &amp; Wikimedia</h4>
        <ul>
          <li><strong>CC BY-SA 3.0:</strong> <a href="https://en.wikipedia.org/" target="_blank" rel="noopener noreferrer">Wikipedia</a> (empire descriptions via REST API)</li>
          <li><strong>Various licenses:</strong> <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener noreferrer">Wikimedia Commons</a> (empire &amp; site images &mdash; individual licenses displayed in lightbox)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>3D Models</h4>
        <ul>
          <li><a href="https://sketchfab.com/" target="_blank" rel="noopener noreferrer">Sketchfab</a> - 3D models are displayed via embed with individual licensing per model. Models are filtered to Cultural Heritage &amp; History category, human-created only.</li>
          <li><strong>CC BY-NC 4.0:</strong> <a href="https://www.cyark.org/" target="_blank" rel="noopener noreferrer">CyArk</a> (non-commercial use only)</li>
          <li><strong>Various (mostly CC BY-NC):</strong> <a href="https://www.morphosource.org/" target="_blank" rel="noopener noreferrer">MorphoSource</a> (check per-item license)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Basemaps &amp; Vector Data</h4>
        <ul>
          <li><strong>Satellite Imagery:</strong> <a href="https://shadedrelief.com/ne-draft/" target="_blank" rel="noopener noreferrer">Shaded Relief / Natural Earth</a></li>
          <li><strong>Vector Layers:</strong> <a href="https://github.com/nvkelso/natural-earth-vector" target="_blank" rel="noopener noreferrer">World-Base-Map-Shapefiles / Natural Earth</a></li>
          <li><strong>Map Tiles:</strong> <a href="https://www.mapbox.com/" target="_blank" rel="noopener noreferrer">Mapbox</a> (satellite imagery and street maps, proprietary - requires Mapbox ToS compliance)</li>
          <li><strong>Site Maps &amp; Street View:</strong> <a href="https://www.google.com/maps" target="_blank" rel="noopener noreferrer">Google Maps</a> (embedded satellite view and Street View panoramas)</li>
          <li><strong>Tectonic Plates:</strong> <a href="https://github.com/fraxen/tectonicplates" target="_blank" rel="noopener noreferrer">fraxen/tectonicplates</a> (based on Peter Bird's PB2002 model)</li>
          <li><strong>Glaciers:</strong> <a href="https://www.glims.org/" target="_blank" rel="noopener noreferrer">GLIMS</a> (Global Land Ice Measurements from Space)</li>
          <li><strong>Coral Reefs:</strong> <a href="https://www.unep-wcmc.org/" target="_blank" rel="noopener noreferrer">UNEP-WCMC</a> (World Conservation Monitoring Centre)</li>
        </ul>
      </div>
      <div class="license-group">
        <h4>Live Webcams</h4>
        <p>Live webcam streams near archaeological sites are provided by <a href="https://www.skylinewebcams.com" target="_blank" rel="noopener noreferrer">SkylineWebcams</a> (VisioRay S.r.l.). All webcam content remains the property of VisioRay S.r.l. and the respective camera operators. Streams are displayed with visible source attribution and link back to SkylineWebcams. This feature is provided for educational purposes to give visitors a real-time view of heritage sites.</p>
      </div>
      <div class="license-group">
        <h4>Country Flags</h4>
        <ul>
          <li><a href="https://flagpedia.net/" target="_blank" rel="noopener noreferrer">Flagpedia</a> via <a href="https://flagcdn.com/" target="_blank" rel="noopener noreferrer">FlagCDN</a></li>
        </ul>
      </div>
    </div>
    <p class="attribution-note">We gratefully acknowledge all data providers and contributors. If you believe any attribution is missing or incorrect, please reach out:</p>
    <div class="contact-links">
      <a href="mailto:ancient.nerds@protonmail.com?subject=Attribution%20Issue">Email</a>
      <a href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer">Discord</a>
    </div>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>Accuracy &amp; Limitations</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <ul>
      <li>Data is aggregated from multiple sources with <strong>varying levels of accuracy and completeness</strong>.</li>
      <li>Coordinate precision varies significantly: some sites are accurate to within meters, others may be approximate within several kilometers.</li>
      <li>Site information may be <strong>outdated, incomplete, or contain errors</strong> from source databases.</li>
      <li>This platform is intended for <strong>educational and research purposes only</strong>.</li>
      <li><strong>Not suitable</strong> for navigation, legal documentation, or official record-keeping.</li>
      <li>Users should always <strong>verify information with primary sources</strong> before relying on it.</li>
    </ul>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>Dating &amp; Chronology</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <h4>Project Scope: Ancient &amp; Classical History</h4>
    <p>This map focuses on <strong>ancient and classical history</strong>. To maintain this focus, we apply regional date cutoffs:</p>
    <ul>
      <li><strong>Old World (Europe, Asia, Africa, Oceania):</strong> Sites dated up to <strong>500 AD</strong> (end of Classical Antiquity)</li>
      <li><strong>Americas:</strong> Sites dated up to <strong>1500 AD</strong> (Pre-Columbian era)</li>
      <li><strong>Sites without dates:</strong> Included (we don't exclude based on missing data)</li>
    </ul>
    <p class="attribution-note">Medieval, Byzantine, and post-classical sites are intentionally excluded to keep the focus on ancient civilizations. Natural hazard events (earthquakes, tsunamis, volcanic eruptions) are filtered to show only historically documented ancient events.</p>
    <h4>Dating Accuracy</h4>
    <ul>
      <li>All dates are <strong>approximate</strong> and based on current archaeological understanding.</li>
      <li>Dating methods vary by site and source (radiocarbon dating, typological analysis, historical records, stratigraphy).</li>
      <li>Period classifications (e.g., &ldquo;Bronze Age&rdquo;, &ldquo;Iron Age&rdquo;) follow conventional regional chronologies which may vary between geographic areas.</li>
      <li>Date ranges are used where precise dates are unknown (e.g., &ldquo;3000-2500 BC&rdquo;).</li>
      <li><strong>BCE/BC</strong> and <strong>CE/AD</strong> notations are used interchangeably across sources.</li>
      <li>New archaeological discoveries may significantly revise accepted dates.</li>
      <li>Some sites span multiple periods; the displayed date may represent initial construction, primary use, or discovery.</li>
    </ul>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>Privacy Policy</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <h4>General</h4>
    <ul>
      <li><strong>No user accounts</strong> are required or stored.</li>
      <li><strong>IP-based geolocation</strong> (via ipwho.is with geojs.io fallback) is used solely to center the globe on your approximate location. Your IP is sent to these third-party services but is not stored or logged by us.</li>
      <li><strong>No cookies</strong> are used for tracking or analytics.</li>
      <li><strong>No personal data</strong> is collected during normal use.</li>
      <li><strong>Contributions:</strong> When you submit a site contribution, the submitted data (site name, coordinates, description) is stored for moderation and may be published if approved. No personal identifiers are attached to contributions.</li>
      <li>We use <strong>Cloudflare Turnstile</strong> for bot protection on the contribution form, which may set technical cookies.</li>
    </ul>
    <h4>AI Pipeline &amp; Third-Party Data Processing</h4>
    <p>Our news pipeline and AI research assistant use third-party services to process <strong>publicly available archaeological data</strong> (YouTube video content, site names, descriptions). No user personal data is sent to these services.</p>
    <ul>
      <li><strong>Mercury 2 API</strong> (Inception Labs) &mdash; Used for content summarization, post generation, fact verification, and site identification via OpenAI-compatible endpoint. Data is processed on US servers by Inception Labs, a US-based company. <a href="https://www.inceptionlabs.ai/privacy" target="_blank" rel="noopener noreferrer">Inception Labs Privacy Policy</a></li>
      <li><strong>Voyage AI</strong> (voyage-4, rerank-2.5-lite) &mdash; Used for embedding site/news data for semantic search. We have <strong>opted out of data training</strong>, which provides zero-day retention (data is deleted immediately after processing). <a href="https://www.voyageai.com/privacy" target="_blank" rel="noopener noreferrer">Voyage AI Privacy Policy</a></li>
      <li><strong>Qdrant</strong> (vector database) &mdash; <strong>Self-hosted</strong> on our infrastructure with telemetry disabled. No data leaves our servers.</li>
    </ul>
    <h4>AI Chat (Research Assistant)</h4>
    <ul>
      <li>Chat queries are processed in real-time via Mercury 2 through the Inception Labs API.</li>
      <li>Conversations are <strong>not stored</strong> on our servers beyond the active session.</li>
      <li>Inception Labs is a US-based company. Data is processed on US servers.</li>
    </ul>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>Fair Use &amp; Licensing</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <h4>Using Our Data</h4>
    <ul>
      <li>Data displayed on this platform is subject to the <strong>original source licenses</strong> listed above.</li>
      <li>Many sources require <strong>attribution</strong> when reusing their data.</li>
      <li>Some sources have <strong>non-commercial restrictions</strong>: Seshat, ToposText, CyArk, MorphoSource, David Rumsey Maps, Earth Impact Database.</li>
      <li>When in doubt, consult the original source&rsquo;s licensing terms.</li>
    </ul>
    <h4>Platform License</h4>
    <ul>
      <li>The Ancient Nerds Research Platform source code is provided under <strong>AGPL-3.0</strong>.</li>
      <li>Original content and documentation are provided under <strong>CC BY-NC-SA 4.0</strong>.</li>
      <li>See <a href="https://github.com/AncientNerds/AncientMap" target="_blank" rel="noopener noreferrer">GitHub</a> for full license details.</li>
    </ul>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>AI-Generated Content</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <p>News feed items are <strong>automatically generated by AI</strong> from publicly available YouTube video content. The AI extracts archaeological facts and presents them in summary form.</p>
    <ul>
      <li>All news content should be treated as <strong>AI-generated summaries</strong>, not original reporting.</li>
      <li>Always verify information by watching the <strong>original video</strong> (linked on each item).</li>
      <li>Summaries may contain inaccuracies &mdash; the original video is always the authoritative source.</li>
      <li>We work with featured channels to ensure proper attribution and link back to every video.</li>
      <li>We highly encourage you to <strong>like, subscribe, and support</strong> the creators whose content appears here &mdash; they are the ones doing the incredible work of bringing archaeology and ancient history to life.</li>
    </ul>
    <h4>YouTube Creator Opt-Out</h4>
    <p>If you are a YouTube creator and would like your channel excluded from our news pipeline, reach out with the subject &ldquo;Channel Opt-Out&rdquo; and your channel name or URL. We will remove your channel within 7 days.</p>
    <div class="contact-links">
      <a href="mailto:ancient.nerds@protonmail.com?subject=Channel%20Opt-Out">Email</a>
      <a href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer">Discord</a>
    </div>
  </div>
</details>

<details class="disclaimer-section">
  <summary class="disclaimer-section-header">
    <span>Contact &amp; Corrections</span>
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chevron"><polyline points="6 9 12 15 18 9"></polyline></svg>
  </summary>
  <div class="disclaimer-section-content">
    <p>We strive for accuracy but errors are inevitable in a database of this scale. If you find:</p>
    <ul>
      <li>Incorrect site information or coordinates</li>
      <li>Missing attributions or licensing concerns</li>
      <li>Duplicate entries or data quality issues</li>
    </ul>
    <p>Please reach out through our community channels:</p>
    <div class="contact-links">
      <a href="mailto:ancient.nerds@protonmail.com">Email</a>
      <a href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer">Discord</a>
      <a href="https://x.com/AncientNerdsDAO" target="_blank" rel="noopener noreferrer">X (Twitter)</a>
    </div>
  </div>
</details>

${footerHTML}
`
}
