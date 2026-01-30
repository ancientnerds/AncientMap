import { useState, memo } from 'react'
import { createPortal } from 'react-dom'

interface DisclaimerModalProps {
  isOpen: boolean
  onClose: () => void
}

interface SectionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function Section({ title, children, defaultOpen = false }: SectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className={`disclaimer-section ${isOpen ? 'open' : ''}`}>
      <button
        className="disclaimer-section-header"
        onClick={() => setIsOpen(!isOpen)}
        type="button"
      >
        <span>{title}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="chevron"
        >
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>
      {isOpen && (
        <div className="disclaimer-section-content">
          {children}
        </div>
      )}
    </div>
  )
}

function DisclaimerModal({ isOpen, onClose }: DisclaimerModalProps) {
  if (!isOpen) return null

  const modalContent = (
    <div className="disclaimer-modal-overlay" onClick={onClose}>
      <div className="disclaimer-modal" onClick={e => e.stopPropagation()}>
        <button className="popup-close" onClick={onClose} title="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <div className="disclaimer-content">
          <h2>Disclaimer & Legal</h2>

          <Section title="Data Sources & Attribution" defaultOpen={true}>
            <p>This platform aggregates archaeological and historical site data from multiple open-source databases. Each source maintains its own licensing terms:</p>

            <div className="source-licenses">
              <div className="license-group">
                <h4>Creative Commons Attribution (CC BY)</h4>
                <ul>
                  <li><strong>CC BY 4.0:</strong> <a href="https://oxrep.classics.ox.ac.uk/databases/shipwrecks_database/" target="_blank" rel="noopener noreferrer">OXREP Shipwrecks</a>, <a href="https://volcano.si.edu/" target="_blank" rel="noopener noreferrer">HolVol Volcanic</a>, <a href="https://www.dinaa.net/" target="_blank" rel="noopener noreferrer">DINAA</a>, <a href="https://eamena.org/" target="_blank" rel="noopener noreferrer">EAMENA</a>, <a href="https://opencontext.org/" target="_blank" rel="noopener noreferrer">Open Context</a>, <a href="http://nomisma.org/" target="_blank" rel="noopener noreferrer">Nomisma Coins</a>, <a href="https://www.geonames.org/" target="_blank" rel="noopener noreferrer">GeoNames</a></li>
                  <li><strong>CC BY 3.0:</strong> <a href="https://pleiades.stoa.org/" target="_blank" rel="noopener noreferrer">Pleiades</a></li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Creative Commons Attribution-ShareAlike</h4>
                <ul>
                  <li><strong>CC BY-SA 4.0:</strong> <a href="https://ancientnerds.com" target="_blank" rel="noopener noreferrer">Ancient Nerds (Original)</a>, <a href="https://www.europeana.eu/" target="_blank" rel="noopener noreferrer">Europeana</a></li>
                  <li><strong>CC BY-SA 3.0:</strong> <a href="https://imperium.ahlfeldt.se/" target="_blank" rel="noopener noreferrer">DARE</a>, <a href="https://edh.ub.uni-heidelberg.de/" target="_blank" rel="noopener noreferrer">EDH Inscriptions</a></li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Creative Commons NonCommercial</h4>
                <ul>
                  <li><strong>CC BY-NC-SA 4.0:</strong> <a href="https://topostext.org/" target="_blank" rel="noopener noreferrer">ToposText</a>, <a href="https://seshat-db.com/" target="_blank" rel="noopener noreferrer">Seshat Global History Databank</a> (empire boundaries, historical data & polity information)</li>
                  <li><strong>CC BY-NC-SA 3.0:</strong> <a href="https://arachne.dainst.org/" target="_blank" rel="noopener noreferrer">Arachne</a>, <a href="https://www.davidrumsey.com/" target="_blank" rel="noopener noreferrer">David Rumsey Maps</a></li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Public Domain & Open Data</h4>
                <ul>
                  <li><strong>CC0 / Public Domain:</strong> <a href="https://www.wikidata.org/" target="_blank" rel="noopener noreferrer">Wikidata</a>, <a href="https://whc.unesco.org/" target="_blank" rel="noopener noreferrer">UNESCO World Heritage</a>, <a href="http://www.passc.net/EarthImpactDatabase/" target="_blank" rel="noopener noreferrer">Earth Impact Database</a>, <a href="https://www.ncei.noaa.gov/maps/hazards/" target="_blank" rel="noopener noreferrer">NCEI Natural Hazards</a></li>
                  <li><strong>CC BY-SA 3.0:</strong> <a href="https://en.wikipedia.org/" target="_blank" rel="noopener noreferrer">Wikipedia</a> (empire descriptions via REST API)</li>
                  <li><strong>Various licenses:</strong> <a href="https://commons.wikimedia.org/" target="_blank" rel="noopener noreferrer">Wikimedia Commons</a> (empire & site images - individual image licenses displayed in lightbox)</li>
                  <li><strong>ODbL:</strong> <a href="https://www.openstreetmap.org/" target="_blank" rel="noopener noreferrer">OpenStreetMap Historic</a></li>
                  <li><strong>Open Government Licence:</strong> <a href="https://historicengland.org.uk/" target="_blank" rel="noopener noreferrer">Historic England</a></li>
                  <li><strong>Open Data:</strong> <a href="https://www.archaeology.ie/" target="_blank" rel="noopener noreferrer">Ireland National Monuments Service</a></li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Various / Mixed Licensing</h4>
                <ul>
                  <li><a href="https://www.megalithic.co.uk/" target="_blank" rel="noopener noreferrer">Megalithic Portal</a>, <a href="https://sacredsites.com/" target="_blank" rel="noopener noreferrer">Sacred Sites</a>, <a href="https://rockartdatabase.com/" target="_blank" rel="noopener noreferrer">Rock Art Database</a></li>
                </ul>
              </div>

              <div className="license-group">
                <h4>3D Models</h4>
                <ul>
                  <li><a href="https://sketchfab.com/" target="_blank" rel="noopener noreferrer">Sketchfab</a> - 3D models are displayed via embed with individual licensing per model. Models are filtered to Cultural Heritage & History category, human-created only.</li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Basemaps & Vector Data</h4>
                <ul>
                  <li><strong>Satellite Imagery:</strong> <a href="https://shadedrelief.com/ne-draft/" target="_blank" rel="noopener noreferrer">Shaded Relief / Natural Earth</a></li>
                  <li><strong>Vector Layers:</strong> <a href="https://github.com/nvkelso/natural-earth-vector" target="_blank" rel="noopener noreferrer">World-Base-Map-Shapefiles / Natural Earth</a></li>
                  <li><strong>Map Tiles:</strong> <a href="https://www.mapbox.com/" target="_blank" rel="noopener noreferrer">Mapbox</a> (satellite imagery and street maps)</li>
                  <li><strong>Site Maps & Street View:</strong> <a href="https://www.google.com/maps" target="_blank" rel="noopener noreferrer">Google Maps</a> (embedded satellite view and Street View panoramas)</li>
                  <li><strong>Tectonic Plates:</strong> <a href="https://github.com/fraxen/tectonicplates" target="_blank" rel="noopener noreferrer">fraxen/tectonicplates</a> (based on Peter Bird's PB2002 model)</li>
                  <li><strong>Glaciers:</strong> <a href="https://www.glims.org/" target="_blank" rel="noopener noreferrer">GLIMS</a> (Global Land Ice Measurements from Space)</li>
                  <li><strong>Coral Reefs:</strong> <a href="https://www.unep-wcmc.org/" target="_blank" rel="noopener noreferrer">UNEP-WCMC</a> (World Conservation Monitoring Centre)</li>
                </ul>
              </div>

              <div className="license-group">
                <h4>Country Flags</h4>
                <ul>
                  <li><a href="https://flagpedia.net/" target="_blank" rel="noopener noreferrer">Flagpedia</a> via <a href="https://flagcdn.com/" target="_blank" rel="noopener noreferrer">FlagCDN</a></li>
                </ul>
              </div>
            </div>

            <p className="attribution-note">
              We gratefully acknowledge all data providers and contributors. If you believe any attribution is missing or incorrect, please contact us.
            </p>
          </Section>

          <Section title="Accuracy & Limitations">
            <ul>
              <li>Data is aggregated from multiple sources with <strong>varying levels of accuracy and completeness</strong>.</li>
              <li>Coordinate precision varies significantly: some sites are accurate to within meters, others may be approximate within several kilometers.</li>
              <li>Site information may be <strong>outdated, incomplete, or contain errors</strong> from source databases.</li>
              <li>This platform is intended for <strong>educational and research purposes only</strong>.</li>
              <li><strong>Not suitable</strong> for navigation, legal documentation, or official record-keeping.</li>
              <li>Users should always <strong>verify information with primary sources</strong> before relying on it.</li>
            </ul>
          </Section>

          <Section title="Dating & Chronology">
            <h4>Project Scope: Ancient & Classical History</h4>
            <p>This map focuses on <strong>ancient and classical history</strong>. To maintain this focus, we apply regional date cutoffs:</p>
            <ul>
              <li><strong>Old World (Europe, Asia, Africa, Oceania):</strong> Sites dated up to <strong>500 AD</strong> (end of Classical Antiquity)</li>
              <li><strong>Americas:</strong> Sites dated up to <strong>1500 AD</strong> (Pre-Columbian era)</li>
              <li><strong>Sites without dates:</strong> Included (we don't exclude based on missing data)</li>
            </ul>
            <p className="attribution-note">
              Medieval, Byzantine, and post-classical sites are intentionally excluded to keep the focus on ancient civilizations. Natural hazard events (earthquakes, tsunamis, volcanic eruptions) are filtered to show only historically documented ancient events.
            </p>

            <h4>Dating Accuracy</h4>
            <ul>
              <li>All dates are <strong>approximate</strong> and based on current archaeological understanding.</li>
              <li>Dating methods vary by site and source (radiocarbon dating, typological analysis, historical records, stratigraphy).</li>
              <li>Period classifications (e.g., "Bronze Age", "Iron Age") follow conventional regional chronologies which may vary between geographic areas.</li>
              <li>Date ranges are used where precise dates are unknown (e.g., "3000-2500 BC").</li>
              <li><strong>BCE/BC</strong> and <strong>CE/AD</strong> notations are used interchangeably across sources.</li>
              <li>New archaeological discoveries may significantly revise accepted dates.</li>
              <li>Some sites span multiple periods; the displayed date may represent initial construction, primary use, or discovery.</li>
            </ul>
          </Section>

          <Section title="Privacy Policy">
            <ul>
              <li><strong>No user accounts</strong> are required or stored.</li>
              <li><strong>IP-based geolocation</strong> (via ipwho.is with geojs.io fallback) is used solely to center the globe on your approximate location. Your IP is sent to these third-party services but is not stored or logged by us.</li>
              <li><strong>No cookies</strong> are used for tracking or analytics.</li>
              <li><strong>No personal data</strong> is collected during normal use.</li>
              <li><strong>Contributions:</strong> When you submit a site contribution, the submitted data (site name, coordinates, description) is stored for moderation and may be published if approved. No personal identifiers are attached to contributions.</li>
              <li>We use <strong>Cloudflare Turnstile</strong> for bot protection on the contribution form, which may set technical cookies.</li>
            </ul>
          </Section>

          <Section title="Fair Use & Licensing">
            <h4>Using Our Data</h4>
            <ul>
              <li>Data displayed on this platform is subject to the <strong>original source licenses</strong> listed above.</li>
              <li>Many sources require <strong>attribution</strong> when reusing their data.</li>
              <li>Some sources have <strong>non-commercial restrictions</strong> (ToposText, Arachne, David Rumsey Maps).</li>
              <li>When in doubt, consult the original source's licensing terms.</li>
            </ul>

            <h4>Platform License</h4>
            <ul>
              <li>The Ancient Nerds Research Platform interface and original content are provided under <strong>CC BY-SA 4.0</strong>.</li>
              <li>You are free to share and adapt for any purpose with appropriate attribution.</li>
            </ul>
          </Section>

          <Section title="Contact & Corrections">
            <p>We strive for accuracy but errors are inevitable in a database of this scale. If you find:</p>
            <ul>
              <li>Incorrect site information or coordinates</li>
              <li>Missing attributions or licensing concerns</li>
              <li>Duplicate entries or data quality issues</li>
            </ul>
            <p>Please reach out through our community channels:</p>
            <div className="contact-links">
              <a href="https://discord.gg/8bAjKKCue4" target="_blank" rel="noopener noreferrer">Discord</a>
              <a href="https://x.com/AncientNerdsDAO" target="_blank" rel="noopener noreferrer">X (Twitter)</a>
            </div>
          </Section>

          <div className="disclaimer-footer">
            <p>Last updated: January 2026</p>
          </div>
        </div>
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}

// Memoize to prevent unnecessary re-renders
export default memo(DisclaimerModal)
