/**
 * useGlobeScene - Three.js scene, camera, renderer, and controls initialization
 * Manages the core Three.js setup for the globe visualization
 *
 * This hook extracts the scene setup code from Globe.tsx (SECTION 1: SCENE SETUP)
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CAMERA, GLOBE, RENDER_ORDER } from '../../config/globeConstants'

export interface SceneRefs {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  controls: OrbitControls
  globe: THREE.Mesh
  points: THREE.Points | null
  backPoints: THREE.Points | null
  shadowPoints: THREE.Points | null
}

interface UseGlobeSceneOptions {
  containerRef: React.RefObject<HTMLDivElement>
  initialPosition?: [number, number] | null  // [lng, lat]
  onSceneReady?: (refs: SceneRefs) => void
  onGpuDetected?: (name: string, isSoftware: boolean) => void
}

// Generate star field geometry
function createStarGeometry(): THREE.BufferGeometry {
  const starGeo = new THREE.BufferGeometry()
  const starCount = 15000
  const positions = new Float32Array(starCount * 3)
  const colors = new Float32Array(starCount * 3)
  const scales = new Float32Array(starCount)

  for (let i = 0; i < starCount; i++) {
    // Random position on a large sphere around the scene
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos((Math.random() * 2) - 1)
    const radius = 50 + Math.random() * 50

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = radius * Math.cos(phi)

    // Star color - mostly white with slight variations
    const brightness = 0.5 + Math.random() * 0.5
    colors[i * 3] = brightness
    colors[i * 3 + 1] = brightness
    colors[i * 3 + 2] = brightness + Math.random() * 0.1 // Slight blue tint

    scales[i] = 0.5 + Math.random() * 1.5
  }

  starGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  starGeo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  starGeo.setAttribute('scale', new THREE.Float32BufferAttribute(scales, 1))

  return starGeo
}

// Create star material
function createStarMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uOpacity: { value: 1.0 },
      uSatelliteMode: { value: 0.0 },
      uGlobeRadius: { value: GLOBE.RADIUS }
    },
    vertexShader: `
      attribute float scale;
      varying vec3 vColor;
      varying float vBehindGlobe;
      uniform float uGlobeRadius;

      void main() {
        vColor = color;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);

        // Check if star is behind globe from camera's perspective
        vec3 starWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;
        vec3 cameraToStar = normalize(starWorldPos - cameraPosition);
        vec3 cameraToOrigin = normalize(-cameraPosition);
        float dot_val = dot(cameraToStar, cameraToOrigin);
        float distToOrigin = length(starWorldPos);
        vBehindGlobe = (dot_val > 0.0 && distToOrigin < length(cameraPosition)) ? 1.0 : 0.0;

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
        if (vBehindGlobe > 0.5) {
          if (uSatelliteMode > 0.5) discard;
          gl_FragColor = vec4(vColor * 0.5, uOpacity * 0.5);
        } else {
          gl_FragColor = vec4(vColor, uOpacity);
        }
      }
    `,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    vertexColors: true
  })
}

// Create basemap geometry (custom sphere matching latLngTo3D formula)
function createBasemapGeometry(radius: number, latSegments: number, lngSegments: number): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  const positions: number[] = []
  const uvs: number[] = []
  const indices: number[] = []

  for (let latIdx = 0; latIdx <= latSegments; latIdx++) {
    const lat = 90 - (latIdx / latSegments) * 180
    const v = latIdx / latSegments

    for (let lngIdx = 0; lngIdx <= lngSegments; lngIdx++) {
      const lng = (lngIdx / lngSegments) * 360 - 180
      const u = lngIdx / lngSegments

      const phi = (90 - lat) * Math.PI / 180
      const theta = (lng + 180) * Math.PI / 180
      const x = -radius * Math.sin(phi) * Math.cos(theta)
      const y = radius * Math.cos(phi)
      const z = radius * Math.sin(phi) * Math.sin(theta)

      positions.push(x, y, z)
      uvs.push(u, 1 - v)
    }
  }

  for (let latIdx = 0; latIdx < latSegments; latIdx++) {
    for (let lngIdx = 0; lngIdx < lngSegments; lngIdx++) {
      const a = latIdx * (lngSegments + 1) + lngIdx
      const b = a + lngSegments + 1
      indices.push(a, b, a + 1)
      indices.push(b, b + 1, a + 1)
    }
  }

  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()

  return geometry
}

export function useGlobeScene(options: UseGlobeSceneOptions) {
  const {
    containerRef,
    initialPosition,
    onSceneReady,
    onGpuDetected
  } = options

  // Scene refs
  const sceneRef = useRef<SceneRefs | null>(null)
  const basemapMeshRef = useRef<THREE.Mesh | null>(null)
  const basemapBackMeshRef = useRef<THREE.Mesh | null>(null)
  const starsRef = useRef<THREE.Group | null>(null)
  const logoSpriteRef = useRef<THREE.Sprite | null>(null)
  const logoMaterialRef = useRef<THREE.SpriteMaterial | null>(null)
  const shaderMaterialsRef = useRef<THREE.ShaderMaterial[]>([])

  // State
  const [sceneReady, setSceneReady] = useState(false)
  const [texturesReady, setTexturesReady] = useState(false)
  const texturesReadyRef = useRef(false)

  // WebGL context handling
  const webglContextLostRef = useRef(false)
  const isPageVisibleRef = useRef(true)
  const needsLabelReloadRef = useRef(false)

  // Warp animation refs
  const warpStartTimeRef = useRef<number | null>(null)
  const warpProgressRef = useRef(0)
  const warpInitialCameraPosRef = useRef<THREE.Vector3 | null>(null)
  const warpTargetCameraPosRef = useRef<THREE.Vector3 | null>(null)
  const warpLinearProgressRef = useRef(0)
  const warpCompleteForLabelsRef = useRef(false)
  const dotsAnimationCompleteRef = useRef(false)
  const logoAnimationStartedRef = useRef(false)

  // Initialize scene
  useEffect(() => {
    const container = containerRef.current
    if (!container || sceneRef.current) return

    let isCleanedUp = false

    // ----- Renderer -----
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: 'high-performance',
      stencil: true,
      depth: true,
      preserveDrawingBuffer: true,
      alpha: true,
      premultipliedAlpha: false
    })
    renderer.setSize(window.innerWidth, window.innerHeight)
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setClearColor(0x000000, 0)
    renderer.domElement.style.background = 'transparent'
    container.appendChild(renderer.domElement)

    // WebGL context loss handling
    const canvas = renderer.domElement
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault()
      webglContextLostRef.current = true
      console.warn('[Globe] WebGL context lost')
    })
    canvas.addEventListener('webglcontextrestored', () => {
      webglContextLostRef.current = false
      needsLabelReloadRef.current = true
      console.log('[Globe] WebGL context restored')
    })

    // Page visibility handling
    const handleVisibilityChange = () => {
      const wasHidden = !isPageVisibleRef.current
      isPageVisibleRef.current = !document.hidden
      if (wasHidden && isPageVisibleRef.current) {
        renderer.render(scene, camera)
        if (needsLabelReloadRef.current) {
          window.dispatchEvent(new CustomEvent('webgl-labels-need-reload'))
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    // GPU detection
    const gl = renderer.getContext()
    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info')
    if (debugInfo) {
      const rendererName = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string
      const angleMatch = rendererName.match(/ANGLE \([^,]+, ([^(]+)/)
      const cleanName = angleMatch ? angleMatch[1].trim() : rendererName
      const softwareRenderers = ['swiftshader', 'llvmpipe', 'mesa offscreen', 'microsoft basic render']
      const isSoftware = softwareRenderers.some(sw => rendererName.toLowerCase().includes(sw))
      onGpuDetected?.(cleanName, isSoftware)
    }

    // ----- Scene and Camera -----
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x000000)

    const camera = new THREE.PerspectiveCamera(
      CAMERA.FOV,
      window.innerWidth / window.innerHeight,
      CAMERA.NEAR,
      CAMERA.FAR
    )

    // Camera initial position
    const startLng = initialPosition?.[0] ?? 10
    const startLat = initialPosition?.[1] ?? 51
    const startDist = CAMERA.MAX_DISTANCE
    const phi = (90 - startLat) * Math.PI / 180
    const theta = (startLng + 180) * Math.PI / 180
    const targetX = -startDist * Math.sin(phi) * Math.cos(theta)
    const targetY = startDist * Math.cos(phi)
    const targetZ = startDist * Math.sin(phi) * Math.sin(theta)
    camera.position.set(-targetX, targetY, -targetZ)
    warpTargetCameraPosRef.current = new THREE.Vector3(targetX, targetY, targetZ)
    warpInitialCameraPosRef.current = new THREE.Vector3(-targetX, targetY, -targetZ)

    // ----- Globe -----
    const globe = new THREE.Mesh(
      new THREE.SphereGeometry(GLOBE.RADIUS, GLOBE.SEGMENTS_THETA, GLOBE.SEGMENTS_PHI),
      new THREE.MeshBasicMaterial({
        color: 0x0a1628,
        transparent: true,
        opacity: 0.8,
        depthWrite: false
      })
    )
    globe.renderOrder = RENDER_ORDER.BASEMAP
    globe.scale.setScalar(0.3)
    scene.add(globe)

    // ----- Basemap -----
    const basemapRadius = 1.0015
    const basemapGeometry = createBasemapGeometry(basemapRadius, 128, 256)
    const basemapMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uGrayBasemap: { value: null },
        uSatellite: { value: null },
        uUseSatellite: { value: false },
        uCameraPos: { value: new THREE.Vector3(0, 0, 2) },
        uOpacity: { value: 0.7 },
        uBasemapOpacity: { value: 1.0 },
        uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
        uTintColor: { value: new THREE.Vector3(0.0, 0.878, 0.816) }
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
          if (uBasemapOpacity < 0.01) discard;
          vec3 toCamera = normalize(uCameraPos);
          vec3 sphereNormal = normalize(vWorldPosition);
          float facing = dot(sphereNormal, toCamera);
          if (facing < 0.0) discard;
          vec3 worldNormal = normalize(vWorldPosition);
          vec3 sunDir = normalize(uSunDirection);
          float rawDiffuse = dot(worldNormal, sunDir);
          float wrapDiffuse = rawDiffuse * 0.5 + 0.5;
          wrapDiffuse = wrapDiffuse * wrapDiffuse;
          float ambient = 0.15;
          float nightAmbient = 0.35;
          float dayFactor = smoothstep(-0.1, 0.3, rawDiffuse);
          float lighting = mix(nightAmbient, ambient + (1.0 - ambient) * wrapDiffuse, dayFactor);
          vec3 viewDir = normalize(uCameraPos - vWorldPosition);
          vec3 halfDir = normalize(sunDir + viewDir);
          float specular = pow(max(dot(worldNormal, halfDir), 0.0), 64.0) * 0.08 * dayFactor;
          vec3 finalColor;
          float finalAlpha;
          if (uUseSatellite) {
            vec3 satColor = texture2D(uSatellite, vUv).rgb;
            finalColor = satColor * lighting + vec3(1.0, 0.95, 0.9) * specular;
            finalAlpha = 1.0;
          } else {
            float grayValue = texture2D(uGrayBasemap, vUv).r;
            float boostedGray = pow(grayValue, 0.8) * 1.3;
            boostedGray = clamp(boostedGray, 0.0, 1.0);
            vec3 tintedColor = uTintColor * boostedGray;
            finalColor = tintedColor;
            finalAlpha = 1.0;
          }
          if (uUseSatellite) {
            float terminator = smoothstep(-0.05, 0.15, rawDiffuse) * smoothstep(0.35, 0.15, rawDiffuse);
            finalColor += vec3(0.4, 0.3, 0.2) * terminator * 0.15;
          }
          gl_FragColor = vec4(finalColor, finalAlpha * uBasemapOpacity);
        }
      `,
      transparent: true,
      depthWrite: false
    })
    const basemapMesh = new THREE.Mesh(basemapGeometry, basemapMaterial)
    basemapMesh.renderOrder = -15
    basemapMesh.visible = false
    basemapMesh.scale.setScalar(0.3)
    scene.add(basemapMesh)
    basemapMeshRef.current = basemapMesh
    shaderMaterialsRef.current.push(basemapMaterial)

    // ----- Stars -----
    const starGeo = createStarGeometry()
    const starMaterial = createStarMaterial()
    const starPoints = new THREE.Points(starGeo, starMaterial)
    const starsGroup = new THREE.Group()
    starsGroup.add(starPoints)
    starsGroup.renderOrder = -30
    camera.add(starsGroup)
    scene.add(camera)
    starsRef.current = starsGroup

    // ----- Logo -----
    const logoImg = new Image()
    logoImg.onload = () => {
      if (isCleanedUp) return
      const canvas = document.createElement('canvas')
      canvas.width = 620
      canvas.height = 500
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.drawImage(logoImg, 0, 0, 620, 500)
        const imageData = ctx.getImageData(0, 0, 620, 500)
        const data = imageData.data
        for (let i = 0; i < data.length; i += 4) {
          if (data[i] > 100) {
            data[i] = 255
            data[i + 1] = 255
            data[i + 2] = 255
          }
        }
        ctx.putImageData(imageData, 0, 0)
        const texture = new THREE.CanvasTexture(canvas)
        const logoMat = new THREE.SpriteMaterial({
          map: texture,
          transparent: true,
          opacity: 0.7,
          color: new THREE.Color(0xc02023),
          depthTest: true,
          depthWrite: false
        })
        const logoSprite = new THREE.Sprite(logoMat)
        const baseLogoHeight = 1.2
        const scale = 0.3
        const logoHeight = baseLogoHeight * scale
        const logoWidth = logoHeight * (620 / 500)
        logoSprite.scale.set(logoWidth, logoHeight, 1)
        logoSprite.position.set(0, 0, 0)
        logoSprite.renderOrder = 0
        scene.add(logoSprite)
        logoSpriteRef.current = logoSprite
        logoMaterialRef.current = logoMat
      }
    }
    logoImg.onerror = (err) => console.error('Failed to load AN logo:', err)
    logoImg.src = '/an-logo.svg'

    // ----- Controls -----
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = CAMERA.DAMPING_FACTOR
    controls.autoRotate = false
    controls.enableRotate = false
    controls.minDistance = CAMERA.MIN_DISTANCE
    controls.maxDistance = CAMERA.MAX_DISTANCE

    // Store refs
    const refs: SceneRefs = {
      renderer,
      scene,
      camera,
      controls,
      globe,
      points: null,
      backPoints: null,
      shadowPoints: null
    }
    sceneRef.current = refs

    setSceneReady(true)
    onSceneReady?.(refs)

    // Cleanup
    return () => {
      isCleanedUp = true
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      controls.dispose()
      renderer.dispose()
      container.removeChild(renderer.domElement)
      sceneRef.current = null
    }
  }, [containerRef, initialPosition, onSceneReady, onGpuDetected])

  // Utility: convert lat/lng to 3D position
  const latLngTo3D = useCallback((lat: number, lng: number, radius: number = 1.002) => {
    const phi = (90 - lat) * Math.PI / 180
    const theta = (lng + 180) * Math.PI / 180
    return new THREE.Vector3(
      -radius * Math.sin(phi) * Math.cos(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.sin(theta)
    )
  }, [])

  // Start warp animation
  const startWarp = useCallback(() => {
    warpStartTimeRef.current = performance.now()
    warpProgressRef.current = 0
    warpLinearProgressRef.current = 0
    logoAnimationStartedRef.current = true
  }, [])

  // Resize handler
  const handleResize = useCallback(() => {
    if (!sceneRef.current) return
    const { camera, renderer } = sceneRef.current
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
    renderer.setSize(window.innerWidth, window.innerHeight)
  }, [])

  return {
    // Core refs
    sceneRef,
    basemapMeshRef,
    basemapBackMeshRef,
    starsRef,
    logoSpriteRef,
    logoMaterialRef,
    shaderMaterialsRef,

    // State
    sceneReady,
    texturesReady,
    setTexturesReady,
    texturesReadyRef,

    // Context refs
    webglContextLostRef,
    isPageVisibleRef,
    needsLabelReloadRef,

    // Warp refs
    warpStartTimeRef,
    warpProgressRef,
    warpInitialCameraPosRef,
    warpTargetCameraPosRef,
    warpLinearProgressRef,
    warpCompleteForLabelsRef,
    dotsAnimationCompleteRef,
    logoAnimationStartedRef,

    // Methods
    latLngTo3D,
    startWarp,
    handleResize
  }
}
