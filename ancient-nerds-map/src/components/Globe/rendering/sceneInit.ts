import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CAMERA, GLOBE, RENDER_ORDER } from '../../../config/globeConstants'

/** Options passed to initializeScene for configuring the scene. */
export interface SceneInitOptions {
  /** Initial camera position [lng, lat] or null for default (Germany ~51N, 10E) */
  initialPosition: [number, number] | null | undefined
  /** Ref callbacks for setting React state / storing refs */
  refs: {
    webglContextLostRef: React.MutableRefObject<boolean>
    needsLabelReloadRef: React.MutableRefObject<boolean>
    isPageVisibleRef: React.MutableRefObject<boolean>
    warpProgressRef: React.MutableRefObject<number>
    warpTargetCameraPosRef: React.MutableRefObject<THREE.Vector3 | null>
    warpInitialCameraPosRef: React.MutableRefObject<THREE.Vector3 | null>
    basemapMeshRef: React.MutableRefObject<THREE.Mesh | null>
    basemapBackMeshRef: React.MutableRefObject<THREE.Mesh | null>
    basemapSectionMeshes: React.MutableRefObject<THREE.Mesh[]>
    shaderMaterialsRef: React.MutableRefObject<THREE.ShaderMaterial[]>
    starsRef: React.MutableRefObject<THREE.Group | null>
    logoSpriteRef: React.MutableRefObject<THREE.Sprite | null>
    logoMaterialRef: React.MutableRefObject<THREE.SpriteMaterial | null>
    logoAnimationStartedRef: React.MutableRefObject<boolean>
    labelGroupRef: React.MutableRefObject<THREE.Group | null>
    splashDoneRef: React.MutableRefObject<boolean | undefined>
  }
  /** State setters */
  setGpuName: (name: string) => void
  setSoftwareRendering: (value: boolean) => void
  setSceneReady: (value: boolean) => void
}

/**
 * All objects created during scene initialization.
 */
export interface SceneResult {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  basemapMesh: THREE.Mesh
  basemapMaterial: THREE.ShaderMaterial
  basemapBackMesh: THREE.Mesh
  basemapBackMaterial: THREE.ShaderMaterial
  sectionMeshes: THREE.Mesh[]
  starsGroup: THREE.Group
  starMaterial: THREE.ShaderMaterial
  labelGroup: THREE.Group
  /** Distance constants from config */
  minDist: number
  maxDist: number
  /** Manual rotation state */
  rotationSpeed: number
  lastFrameTime: number
  /** Visibility change handler (needed for cleanup) */
  handleVisibilityChange: () => void
  /** Cleanup flag setter - call with true during effect cleanup */
  isCleanedUp: { value: boolean }
}

/**
 * Initializes the entire Three.js scene including renderer, camera, globe mesh,
 * basemap, starfield, logo, orbit controls, and label group.
 */
export function initializeScene(
  container: HTMLElement,
  options: SceneInitOptions
): SceneResult {
  const { initialPosition, refs, setGpuName, setSoftwareRendering, setSceneReady } = options

  // Cleanup flag to prevent stale async callbacks (logo loading, texture loading, etc.)
  // from running after this effect instance is cleaned up (React strict mode, remounts)
  const isCleanedUp = { value: false }

  // Zoom distance constants from config
  const minDist = CAMERA.MIN_DISTANCE
  const maxDist = CAMERA.MAX_DISTANCE

  // WebGL Renderer
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
    stencil: true,  // Enable stencil buffer for even-odd polygon fill
    depth: true,
    preserveDrawingBuffer: true,  // Required for screenshot capture
    alpha: true,  // Transparent background so Mapbox GL shows through
    premultipliedAlpha: false  // Required for proper alpha compositing with Mapbox behind
  })
  renderer.setSize(window.innerWidth, window.innerHeight)
  renderer.setPixelRatio(window.devicePixelRatio)
  // Make Three.js canvas transparent so Mapbox shows through
  renderer.setClearColor(0x000000, 0)
  renderer.domElement.style.background = 'transparent'
  container.appendChild(renderer.domElement)

  // Handle WebGL context loss (prevents crash on memory pressure / tab backgrounding)
  const canvas = renderer.domElement
  canvas.addEventListener('webglcontextlost', (e) => {
    e.preventDefault()
    refs.webglContextLostRef.current = true
    console.warn('[Globe] WebGL context lost - will recover when restored')
  })
  canvas.addEventListener('webglcontextrestored', () => {
    console.log('[Globe] WebGL context restored - scheduling label reload')
    refs.webglContextLostRef.current = false
    // Labels need to be reloaded as their textures were lost
    refs.needsLabelReloadRef.current = true
  })

  // Scene and Camera
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x000000) // Black space

  // Camera - start looking at user location (from IP) or fallback to central Germany (~51N, 10E)
  const camera = new THREE.PerspectiveCamera(CAMERA.FOV, window.innerWidth / window.innerHeight, CAMERA.NEAR, CAMERA.FAR)

  // Page Visibility API - pause rendering when tab is hidden to save resources
  // and prevent state corruption from long background periods
  const handleVisibilityChange = () => {
    const wasHidden = !refs.isPageVisibleRef.current
    refs.isPageVisibleRef.current = !document.hidden
    if (wasHidden && refs.isPageVisibleRef.current) {
      console.log('[Globe] Tab became visible - resuming')
      // Force a render to refresh the display
      renderer.render(scene, camera)
      // Check if labels need recovery (context was lost while hidden)
      if (refs.needsLabelReloadRef.current) {
        console.log('[Globe] Triggering label recovery after context restore')
        // Dispatch custom event that the label loading effect will catch
        window.dispatchEvent(new CustomEvent('webgl-labels-need-reload'))
      }
    } else if (!refs.isPageVisibleRef.current) {
      console.log('[Globe] Tab hidden - pausing render loop')
    }
  }
  document.addEventListener('visibilitychange', handleVisibilityChange)

  // Detect GPU and software rendering (hardware acceleration disabled)
  const gl = renderer.getContext()
  const debugInfo = gl.getExtension('WEBGL_debug_renderer_info')
  if (debugInfo) {
    const rendererName = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string
    console.log('[GPU] Renderer:', rendererName)

    // Extract clean GPU name from ANGLE string like "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 ...)"
    const angleMatch = rendererName.match(/ANGLE \([^,]+, ([^(]+)/)
    const cleanName = angleMatch ? angleMatch[1].trim() : rendererName
    setGpuName(cleanName)

    const softwareRenderers = ['swiftshader', 'llvmpipe', 'mesa offscreen', 'microsoft basic render']
    const isSoftware = softwareRenderers.some(sw => rendererName.toLowerCase().includes(sw))
    if (isSoftware) {
      console.warn('[GPU] Software rendering detected - hardware acceleration may be disabled')
      setSoftwareRendering(true)
    }
  }

  // Use initialPosition if provided, otherwise fallback to Germany
  const startLng = initialPosition?.[0] ?? 10
  const startLat = initialPosition?.[1] ?? 51
  const startDist = CAMERA.MAX_DISTANCE // maxDist = 0% zoom
  const phi = (90 - startLat) * Math.PI / 180
  const theta = (startLng + 180) * Math.PI / 180
  // Calculate user's target position
  const targetX = -startDist * Math.sin(phi) * Math.cos(theta)
  const targetY = startDist * Math.cos(phi)
  const targetZ = startDist * Math.sin(phi) * Math.sin(theta)
  // Start camera at OPPOSITE side (180 rotated) for warp-in effect
  // This prevents the visible jump when warp starts
  camera.position.set(-targetX, targetY, -targetZ)
  // Store target position for warp animation to use
  refs.warpTargetCameraPosRef.current = new THREE.Vector3(targetX, targetY, targetZ)
  refs.warpInitialCameraPosRef.current = new THREE.Vector3(-targetX, targetY, -targetZ)

  // Globe base (deep blue ocean - coastlines define land boundaries)
  const globe = new THREE.Mesh(
    new THREE.SphereGeometry(GLOBE.RADIUS, GLOBE.SEGMENTS_THETA, GLOBE.SEGMENTS_PHI),
    new THREE.MeshBasicMaterial({
      color: 0x0a1628, // Deep blue
      transparent: true,
      opacity: 0.8,
      depthWrite: false // Don't block logo inside
    })
  )
  globe.renderOrder = RENDER_ORDER.BASEMAP // Render first
  globe.scale.setScalar(0.3) // Start small for warp-in effect
  scene.add(globe)

  // Basemap Mesh - add base map mesh (for satellite/street textures)
  // Custom sphere geometry using SAME coordinate formula as coastlines (no parallax)
  const basemapRadius = 1.0015 // Slightly below vector layers (1.002)
  const latSegments = 128
  const lngSegments = 256
  const basemapGeometry = new THREE.BufferGeometry()
  const positions: number[] = []
  const uvs: number[] = []
  const indices: number[] = []

  // Generate vertices using exact same formula as latLngTo3D
  for (let latIdx = 0; latIdx <= latSegments; latIdx++) {
    const lat = 90 - (latIdx / latSegments) * 180 // 90 to -90
    const v = latIdx / latSegments // UV v: 0 at north pole, 1 at south pole

    for (let lngIdx = 0; lngIdx <= lngSegments; lngIdx++) {
      const lng = (lngIdx / lngSegments) * 360 - 180 // -180 to 180
      const u = lngIdx / lngSegments // UV u: 0 at -180, 1 at 180

      // Exact same formula as latLngTo3D
      const phi = (90 - lat) * Math.PI / 180
      const theta = (lng + 180) * Math.PI / 180
      const x = -basemapRadius * Math.sin(phi) * Math.cos(theta)
      const y = basemapRadius * Math.cos(phi)
      const z = basemapRadius * Math.sin(phi) * Math.sin(theta)

      positions.push(x, y, z)
      uvs.push(u, 1 - v) // Flip v for correct texture orientation
    }
  }

  // Generate triangle indices
  for (let latIdx = 0; latIdx < latSegments; latIdx++) {
    for (let lngIdx = 0; lngIdx < lngSegments; lngIdx++) {
      const a = latIdx * (lngSegments + 1) + lngIdx
      const b = a + lngSegments + 1
      indices.push(a, b, a + 1)
      indices.push(b, b + 1, a + 1)
    }
  }

  basemapGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  basemapGeometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
  basemapGeometry.setIndex(indices)
  basemapGeometry.computeVertexNormals()

  const basemapMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uGrayBasemap: { value: null },
      uSatellite: { value: null },
      uUseSatellite: { value: false },
      uCameraPos: { value: new THREE.Vector3(0, 0, 2) },
      uOpacity: { value: 0.7 },           // Transparency for tinted relief mode
      uBasemapOpacity: { value: 1.0 },    // Opacity for Mapbox tile blending (1 = full, 0 = hidden)
      uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
      uTintColor: { value: new THREE.Vector3(0.0, 0.878, 0.816) } // Teal #00E0D0 (matches coastlines)
    },
    vertexShader: `
      varying vec2 vUv;
      varying vec3 vWorldPosition;
      varying vec3 vNormal;

      void main() {
        vUv = uv;
        vNormal = normalize(normalMatrix * normal);
        vec4 worldPos = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPos.xyz;
        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform sampler2D uGrayBasemap;
      uniform sampler2D uSatellite;
      uniform bool uUseSatellite;
      uniform vec3 uCameraPos;
      uniform float uOpacity;
      uniform float uBasemapOpacity;
      uniform vec3 uSunDirection;
      uniform vec3 uTintColor;

      varying vec2 vUv;
      varying vec3 vWorldPosition;
      varying vec3 vNormal;

      void main() {
        // Early exit if basemap is fully transparent (Mapbox tiles visible)
        if (uBasemapOpacity < 0.01) discard;

        vec3 toCamera = normalize(uCameraPos);
        vec3 sphereNormal = normalize(vWorldPosition);
        float facing = dot(sphereNormal, toCamera);

        // Backface culling - backside handled by separate mesh
        if (facing < 0.0) discard;

        // Use sphere position as normal (for sphere centered at origin, position = normal)
        // This ensures lighting is fixed to globe surface, not affected by any transforms
        vec3 worldNormal = normalize(vWorldPosition);

        // Real-time sun position - absolute world space (not camera-relative)
        vec3 sunDir = normalize(uSunDirection);

        // Soft wrap lighting (half-lambert) for diffuse sun-like illumination
        float rawDiffuse = dot(worldNormal, sunDir);
        float wrapDiffuse = rawDiffuse * 0.5 + 0.5; // Wrap to 0-1 range for softer falloff
        wrapDiffuse = wrapDiffuse * wrapDiffuse; // Square for subtle falloff curve

        // Ambient lighting levels
        float ambient = 0.15;
        float nightAmbient = 0.35; // Brighter night side for visibility

        // Smooth day/night transition
        float dayFactor = smoothstep(-0.1, 0.3, rawDiffuse); // Gradual transition at terminator

        // Combine lighting - softer overall
        float lighting = mix(nightAmbient, ambient + (1.0 - ambient) * wrapDiffuse, dayFactor);

        // Very subtle specular (sun glints on water/ice, not harsh)
        vec3 viewDir = normalize(uCameraPos - vWorldPosition);
        vec3 halfDir = normalize(sunDir + viewDir);
        float specular = pow(max(dot(worldNormal, halfDir), 0.0), 64.0) * 0.08 * dayFactor;

        vec3 finalColor;
        float finalAlpha;

        if (uUseSatellite) {
          // Satellite mode: full color texture with sun lighting
          vec3 satColor = texture2D(uSatellite, vUv).rgb;
          finalColor = satColor * lighting + vec3(1.0, 0.95, 0.9) * specular;
          finalAlpha = 1.0;
        } else {
          // Relief mode: grayscale basemap with teal tint, no sun lighting
          // Boosted brightness (1.3x) and contrast (gamma 0.8) for better visibility
          float grayValue = texture2D(uGrayBasemap, vUv).r;
          float boostedGray = pow(grayValue, 0.8) * 1.3;
          boostedGray = clamp(boostedGray, 0.0, 1.0);
          vec3 tintedColor = uTintColor * boostedGray;
          finalColor = tintedColor;
          finalAlpha = 1.0;  // Fully opaque (was 0.95)
        }

        // Atmospheric scattering at terminator (dawn/dusk glow) - only for satellite mode
        if (uUseSatellite) {
          float terminator = smoothstep(-0.05, 0.15, rawDiffuse) * smoothstep(0.35, 0.15, rawDiffuse);
          finalColor += vec3(0.4, 0.3, 0.2) * terminator * 0.15;
        }

        // Apply basemap opacity for Mapbox tile blending
        gl_FragColor = vec4(finalColor, finalAlpha * uBasemapOpacity);
      }
    `,
    transparent: true,  // Enable transparency for Mapbox tile blending
    depthWrite: false  // Don't block vector layers
    // Note: Land mask stencil test disabled - needs debugging
  })
  const basemapMesh = new THREE.Mesh(basemapGeometry, basemapMaterial)
  basemapMesh.renderOrder = -15 // Between globe and vector layers
  basemapMesh.visible = false // Hidden until texture loaded
  basemapMesh.scale.setScalar(0.3) // Start small for warp-in effect
  scene.add(basemapMesh)
  refs.basemapMeshRef.current = basemapMesh
  refs.shaderMaterialsRef.current.push(basemapMaterial) // Register for camera updates

  // Create back-facing basemap mesh for glass blur effect
  const basemapBackMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uGrayBasemap: { value: null },
      uSatellite: { value: null },
      uUseSatellite: { value: false },
      uCameraPos: { value: new THREE.Vector3(0, 0, 2) },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 },
      uTintColor: { value: new THREE.Vector3(0.0, 0.878, 0.816) }, // Teal #00E0D0 (matches coastlines)
      uTexelSize: { value: new THREE.Vector2(1.0 / 32400, 1.0 / 16200) }
    },
    vertexShader: `
      varying vec2 vUv;
      varying vec3 vWorldPosition;

      void main() {
        vUv = uv;
        vec4 worldPos = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPos.xyz;
        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform sampler2D uGrayBasemap;
      uniform sampler2D uSatellite;
      uniform bool uUseSatellite;
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      uniform float uHideBackside;
      uniform vec3 uTintColor;
      uniform vec2 uTexelSize;

      varying vec2 vUv;
      varying vec3 vWorldPosition;

      // 5x5 Gaussian blur kernel (approximated with 13 samples for performance)
      vec3 blurSample(sampler2D tex, vec2 uv, vec2 texelSize, float blurRadius) {
        vec3 result = vec3(0.0);
        float totalWeight = 0.0;

        // Center sample (weight 4)
        result += texture2D(tex, uv).rgb * 4.0;
        totalWeight += 4.0;

        // Inner ring (weight 2) - 4 samples
        vec2 offset1 = texelSize * blurRadius;
        result += texture2D(tex, uv + vec2(offset1.x, 0.0)).rgb * 2.0;
        result += texture2D(tex, uv - vec2(offset1.x, 0.0)).rgb * 2.0;
        result += texture2D(tex, uv + vec2(0.0, offset1.y)).rgb * 2.0;
        result += texture2D(tex, uv - vec2(0.0, offset1.y)).rgb * 2.0;
        totalWeight += 8.0;

        // Outer ring (weight 1) - 8 samples
        vec2 offset2 = texelSize * blurRadius * 2.0;
        result += texture2D(tex, uv + vec2(offset2.x, 0.0)).rgb;
        result += texture2D(tex, uv - vec2(offset2.x, 0.0)).rgb;
        result += texture2D(tex, uv + vec2(0.0, offset2.y)).rgb;
        result += texture2D(tex, uv - vec2(0.0, offset2.y)).rgb;
        result += texture2D(tex, uv + vec2(offset2.x, offset2.y) * 0.707).rgb;
        result += texture2D(tex, uv + vec2(-offset2.x, offset2.y) * 0.707).rgb;
        result += texture2D(tex, uv + vec2(offset2.x, -offset2.y) * 0.707).rgb;
        result += texture2D(tex, uv + vec2(-offset2.x, -offset2.y) * 0.707).rgb;
        totalWeight += 8.0;

        return result / totalWeight;
      }

      void main() {
        vec3 toCamera = normalize(uCameraPos);
        vec3 sphereNormal = normalize(vWorldPosition);
        float facing = dot(sphereNormal, toCamera);
        float horizon = 1.0 / uCameraDist;  // Same as other materials

        // Only render backside (below horizon)
        if (facing >= horizon) discard;

        // Fade out when zoomed in
        float fadeOut = 1.0 - uHideBackside;
        if (fadeOut < 0.01) discard;

        // Frosted glass overlay on top of back elements
        // Semi-transparent to blur/soften everything behind
        vec3 frostColor = vec3(0.06, 0.12, 0.16);

        // 70% opacity - strong frost but still see shapes through
        gl_FragColor = vec4(frostColor, 0.7 * fadeOut);
      }
    `,
    transparent: true,
    depthWrite: false,
    depthTest: true,   // Normal depth testing
    side: THREE.FrontSide  // Only render front faces - shader discards front-of-globe
  })
  // Back basemap mesh - disabled (no blur effect needed, just darker elements)
  const basemapBackMesh = new THREE.Mesh(basemapGeometry, basemapBackMaterial)
  basemapBackMesh.renderOrder = -17
  basemapBackMesh.visible = false // Disabled - not needed
  basemapBackMesh.scale.setScalar(0.3) // Start small for warp-in effect
  scene.add(basemapBackMesh)
  refs.basemapBackMeshRef.current = basemapBackMesh
  // Don't register for updates - not used

  // Create 4 section meshes for high-detail mode (each covers 90 longitude)
  const sectionMeshes: THREE.Mesh[] = []
  for (let section = 0; section < 4; section++) {
    const sectionGeometry = new THREE.BufferGeometry()
    const sectionPositions: number[] = []
    const sectionUvs: number[] = []
    const sectionIndices: number[] = []
    const sectionLatSegs = 64
    const sectionLngSegs = 64
    const lngStart = -180 + section * 90 // -180, -90, 0, 90 (each section covers 90)

    for (let latIdx = 0; latIdx <= sectionLatSegs; latIdx++) {
      const lat = 90 - (latIdx / sectionLatSegs) * 180
      const v = latIdx / sectionLatSegs

      for (let lngIdx = 0; lngIdx <= sectionLngSegs; lngIdx++) {
        const lng = lngStart + (lngIdx / sectionLngSegs) * 90
        const u = lngIdx / sectionLngSegs

        const phi = (90 - lat) * Math.PI / 180
        const theta = (lng + 180) * Math.PI / 180
        const x = -basemapRadius * Math.sin(phi) * Math.cos(theta)
        const y = basemapRadius * Math.cos(phi)
        const z = basemapRadius * Math.sin(phi) * Math.sin(theta)

        sectionPositions.push(x, y, z)
        sectionUvs.push(u, 1 - v)
      }
    }

    for (let latIdx = 0; latIdx < sectionLatSegs; latIdx++) {
      for (let lngIdx = 0; lngIdx < sectionLngSegs; lngIdx++) {
        const a = latIdx * (sectionLngSegs + 1) + lngIdx
        const b = a + sectionLngSegs + 1
        sectionIndices.push(a, b, a + 1)
        sectionIndices.push(b, b + 1, a + 1)
      }
    }

    sectionGeometry.setAttribute('position', new THREE.Float32BufferAttribute(sectionPositions, 3))
    sectionGeometry.setAttribute('uv', new THREE.Float32BufferAttribute(sectionUvs, 2))
    sectionGeometry.setIndex(sectionIndices)
    sectionGeometry.computeVertexNormals()

    const sectionMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uGrayBasemap: { value: null },
        uSatellite: { value: null },
        uUseSatellite: { value: false },
        uCameraPos: { value: new THREE.Vector3(0, 0, 2) },
        uOpacity: { value: 0.7 },
        uBasemapOpacity: { value: 1.0 },  // Opacity for Mapbox tile blending
        uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
        uTintColor: { value: new THREE.Vector3(0.0, 0.878, 0.816) } // Teal #00E0D0 (matches coastlines)
      },
      vertexShader: basemapMaterial.vertexShader,
      fragmentShader: basemapMaterial.fragmentShader,
      transparent: true,  // Enable transparency for Mapbox tile blending
      depthWrite: false  // Don't block vector layers
      // Note: Land mask stencil test disabled - needs debugging
    })

    const sectionMesh = new THREE.Mesh(sectionGeometry, sectionMaterial)
    sectionMesh.renderOrder = -15
    sectionMesh.visible = false
    sectionMesh.scale.setScalar(0.3) // Start small for warp-in effect
    scene.add(sectionMesh)
    sectionMeshes.push(sectionMesh)
    refs.shaderMaterialsRef.current.push(sectionMaterial)
  }
  refs.basemapSectionMeshes.current = sectionMeshes
  setSceneReady(true) // Trigger texture loading

  // Starfield Background - add stars in separate group for independent rotation
  const starCount = 2000
  const starPositions = new Float32Array(starCount * 3)
  const starColors = new Float32Array(starCount * 3)
  for (let i = 0; i < starCount; i++) {
    // Random position on a large sphere
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const r = 800 + Math.random() * 400 // Distance 800-1200 (very far)
    starPositions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    starPositions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    starPositions[i * 3 + 2] = r * Math.cos(phi)
    // Slight color variation (white to light blue)
    const brightness = 0.5 + Math.random() * 0.5
    starColors[i * 3] = brightness
    starColors[i * 3 + 1] = brightness
    starColors[i * 3 + 2] = brightness + Math.random() * 0.2
  }
  const starGeo = new THREE.BufferGeometry()
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3))
  starGeo.setAttribute('color', new THREE.BufferAttribute(starColors, 3))
  // Custom shader for stars - dims behind globe, hides when satellite active
  const starMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uCameraDist: { value: CAMERA.INITIAL_DISTANCE },
      uSatelliteMode: { value: 0.0 },
      uOpacity: { value: 1.0 },
      uGlobeScale: { value: 0.3 }  // Globe scale during warp (0.3 to 1.0)
    },
    vertexShader: `
      attribute vec3 color;
      varying vec3 vColor;
      varying float vBehindGlobe;
      uniform float uCameraDist;
      uniform float uGlobeScale;

      void main() {
        vColor = color;

        // Star position in view space
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vec3 viewPos = mvPosition.xyz;

        // Globe center in view space (globe is at world origin, camera looks at it)
        // In view space, globe is at (0, 0, -cameraDist)
        vec3 globeCenter = vec3(0.0, 0.0, -uCameraDist);
        float globeRadius = uGlobeScale;  // Use actual globe scale during warp

        // Ray from camera (origin) toward star
        vec3 rayDir = normalize(viewPos);

        // Ray-sphere intersection test
        vec3 L = globeCenter; // origin is at 0
        float tca = dot(L, rayDir);
        float d2 = dot(L, L) - tca * tca;
        float r2 = globeRadius * globeRadius;

        // Check if ray intersects globe and star is behind it
        if (d2 < r2 && tca > 0.0) {
          // Ray intersects sphere, check if star is behind intersection
          float thc = sqrt(r2 - d2);
          float t0 = tca - thc; // near intersection
          float starDist = length(viewPos);
          vBehindGlobe = starDist > t0 ? 1.0 : 0.0;
        } else {
          vBehindGlobe = 0.0;
        }

        gl_PointSize = 1.5;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vBehindGlobe;
      uniform float uSatelliteMode;
      uniform float uOpacity;

      void main() {
        // Stars behind globe handling:
        // - Satellite ON: completely hide (opaque satellite blocks them)
        // - Satellite OFF: dim to 50%
        if (vBehindGlobe > 0.5) {
          if (uSatelliteMode > 0.5) discard; // Satellite is opaque, block completely
          // Non-satellite: dim to 50%
          gl_FragColor = vec4(vColor * 0.5, uOpacity * 0.5);
        } else {
          // Stars not behind globe - full brightness
          gl_FragColor = vec4(vColor, uOpacity);
        }
      }
    `,
    transparent: true,
    depthTest: false,
    depthWrite: false
  })
  const starPoints = new THREE.Points(starGeo, starMaterial)
  const starsGroup = new THREE.Group()
  starsGroup.add(starPoints)
  starsGroup.renderOrder = -30 // Behind everything
  camera.add(starsGroup) // Attach to camera so stars never move with globe rotation
  scene.add(camera) // Camera must be in scene for its children to render
  refs.starsRef.current = starsGroup

  // Center Logo (Watermark) - add AN logo at center of globe, watermark style, always facing viewer
  // Starts RED, pops to GREEN at warp start, then fades to transparent during warp
  const logoImg = new Image()
  logoImg.onload = () => {
    // Don't run if effect was cleaned up (React strict mode, remounts)
    if (isCleanedUp.value) return

    // SVG viewBox is 620x500, preserve aspect ratio
    const canvas = document.createElement('canvas')
    canvas.width = 620
    canvas.height = 500
    const ctx = canvas.getContext('2d')
    if (ctx) {
      // Draw logo and convert to white (so we can colorize with material.color)
      ctx.drawImage(logoImg, 0, 0, 620, 500)

      // Convert red logo to white, preserving alpha
      const imageData = ctx.getImageData(0, 0, 620, 500)
      const data = imageData.data
      for (let i = 0; i < data.length; i += 4) {
        // If pixel has any red (logo pixels), make it white
        if (data[i] > 100) { // Red channel > 100 means it's part of the logo
          data[i] = 255     // R
          data[i + 1] = 255 // G
          data[i + 2] = 255 // B
          // Keep alpha as-is
        }
      }
      ctx.putImageData(imageData, 0, 0)

      const texture = new THREE.CanvasTexture(canvas)

      // Use Sprite for automatic billboard effect (always faces camera)
      // Start with RED color, will transition to GREEN during warp
      const logoMat = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        opacity: 0.7, // Start at 30% transparency (70% opacity)
        color: new THREE.Color(0xc02023), // Start red (matches loading screen)
        depthTest: true,
        depthWrite: false
      })
      const logoSprite = new THREE.Sprite(logoMat)
      // SVG viewBox is 620x500, aspect ratio = 1.24
      // Use current warp progress to set initial scale (in case logo loads mid-animation)
      const currentProgress = refs.warpProgressRef.current
      const baseLogoHeight = 1.2
      const scale = 0.3 + currentProgress * 0.7 // 0.3 to 1.0
      const logoHeight = baseLogoHeight * scale
      const logoWidth = logoHeight * (620 / 500) // Match SVG aspect ratio
      logoSprite.scale.set(logoWidth, logoHeight, 1)
      logoSprite.position.set(0, 0, 0) // Center of globe
      logoSprite.renderOrder = 0 // Between back lines (-10) and front lines (10)
      scene.add(logoSprite) // Add to scene, not globe, so it doesn't rotate

      // Also set opacity and color based on current progress (in case logo loads mid-animation)
      // Start at 70% opacity (30% transparency) and fade from there
      const exponentialFade = 0.7 * Math.pow(1 - currentProgress, 3)
      logoMat.opacity = Math.max(exponentialFade, 0.02)
      // Color transition: red -> green with pop effect in first 20% of animation
      const colorProgress = Math.min(currentProgress / 0.2, 1.0)
      const popEase = colorProgress < 1 ? 1 - Math.pow(1 - colorProgress, 3) : 1 // Cubic ease-out for pop
      logoMat.color.setRGB(
        0.75 * (1 - popEase) + 0.0 * popEase,  // Red: 0.75 -> 0
        0.13 * (1 - popEase) + 0.88 * popEase, // Green: 0.13 -> 0.88
        0.14 * (1 - popEase) + 0.64 * popEase  // Blue: 0.14 -> 0.64 (teal-green)
      )

      // Store refs for animation loop to update during warp
      refs.logoSpriteRef.current = logoSprite
      refs.logoMaterialRef.current = logoMat
      console.log(`[Logo] Loaded and initialized. Current warp progress: ${currentProgress.toFixed(2)}, splashDone: ${refs.splashDoneRef.current}`)
    }
  }
  logoImg.onerror = (err) => console.error('Failed to load AN logo:', err)
  logoImg.src = '/an-logo.svg'

  // OrbitControls Setup (using constants from config)
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = CAMERA.DAMPING_FACTOR
  controls.autoRotate = false // We'll handle rotation manually for frame-rate independence
  controls.enableRotate = false // Custom arcball rotation
  controls.minDistance = CAMERA.MIN_DISTANCE
  controls.maxDistance = CAMERA.MAX_DISTANCE

  // Manual rotation state (frame-rate independent)
  const rotationSpeed = 0.01 // Radians per second (slow gentle spin)
  const lastFrameTime = performance.now()

  // Label Group for site labels
  const labelGroup = new THREE.Group()
  scene.add(labelGroup)
  refs.labelGroupRef.current = labelGroup

  return {
    renderer,
    scene,
    camera,
    controls,
    globe,
    basemapMesh,
    basemapMaterial,
    basemapBackMesh,
    basemapBackMaterial,
    sectionMeshes,
    starsGroup,
    starMaterial,
    labelGroup,
    minDist,
    maxDist,
    rotationSpeed,
    lastFrameTime,
    handleVisibilityChange,
    isCleanedUp,
  }
}
