import * as THREE from 'three'

/**
 * Stencil material for fan triangulation - writes to stencil buffer only
 * Used for even-odd fill rule polygon rendering of empire territories
 */
export function createStencilMaterial(): THREE.ShaderMaterial {
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uCameraPos: { value: new THREE.Vector3() },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 },
      uSatelliteEnabled: { value: false }
    },
    vertexShader: `
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      varying float vFacing;
      varying float vHorizon;

      void main() {
        vec4 worldPos = modelMatrix * vec4(position, 1.0);
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(worldPos.xyz);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;
        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform float uHideBackside;
      uniform bool uSatelliteEnabled;
      varying float vFacing;
      varying float vHorizon;

      void main() {
        bool isBackside = vFacing < vHorizon * 0.8;
        // In satellite mode, discard backside entirely
        if (isBackside && uSatelliteEnabled) discard;
        // When zoomed in (hideBackside = 1), also discard backside
        if (isBackside && uHideBackside > 0.99) discard;
        gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);  // Doesn't matter, colorWrite is false
      }
    `,
    transparent: false,
    depthWrite: false,
    depthTest: true,
    colorWrite: false,  // Don't write to color buffer
    side: THREE.DoubleSide,
    stencilWrite: true,
    stencilFunc: THREE.AlwaysStencilFunc,
    stencilRef: 1,
    stencilZPass: THREE.InvertStencilOp,  // XOR/Invert for even-odd fill rule
    stencilZFail: THREE.KeepStencilOp,
    stencilFail: THREE.KeepStencilOp
  })
  return mat
}

/**
 * Stencil material for LAND MASK - writes stencil value to mark land areas
 * Used to cut oceans from basemap texture (only show texture on land)
 */
export function createLandMaskStencilMaterial(): THREE.ShaderMaterial {
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uCameraPos: { value: new THREE.Vector3() },
      uCameraDist: { value: 2.2 }
    },
    vertexShader: `
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      varying float vFacing;
      varying float vHorizon;

      void main() {
        vec4 worldPos = modelMatrix * vec4(position, 1.0);
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(worldPos.xyz);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;
        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      varying float vFacing;
      varying float vHorizon;

      void main() {
        // Only process front-facing fragments (facing camera)
        if (vFacing < vHorizon * 0.8) discard;
        gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);  // Doesn't matter, colorWrite is false
      }
    `,
    transparent: false,
    depthWrite: false,
    depthTest: true,
    colorWrite: false,  // Don't write to color buffer
    side: THREE.DoubleSide,
    stencilWrite: true,
    stencilFunc: THREE.AlwaysStencilFunc,
    stencilRef: 1,
    stencilZPass: THREE.ReplaceStencilOp,  // Write 1 wherever land is (simple replace, not XOR)
    stencilZFail: THREE.KeepStencilOp,
    stencilFail: THREE.KeepStencilOp
  })
  return mat
}

/**
 * Fill material that tests stencil buffer for empire territories
 * Uses additive blending so overlapping empires mix colors together
 * Features: sun lighting boost for satellite mode
 */
export function createEmpireFillMaterial(color: number, opacity: number = 0.15): THREE.ShaderMaterial {
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uCameraPos: { value: new THREE.Vector3() },
      uOpacity: { value: opacity },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 },
      uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
      uSatelliteEnabled: { value: false }
    },
    vertexShader: `
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      varying vec3 vWorldPosition;
      varying float vFacing;
      varying float vHorizon;

      void main() {
        vec4 worldPos = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPos.xyz;
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(worldPos.xyz);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;
        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform float uHideBackside;
      uniform vec3 uSunDirection;
      uniform bool uSatelliteEnabled;
      varying vec3 vWorldPosition;
      varying float vFacing;
      varying float vHorizon;

      void main() {
        if (uOpacity < 0.01) discard;  // Hide when opacity is 0
        bool isBackside = vFacing < vHorizon;

        // In satellite mode, discard backside. Otherwise dim it.
        if (isBackside && uSatelliteEnabled) discard;

        // Calculate backside fade (blend between dimmed and hidden based on uHideBackside)
        float backsideFade = 1.0;
        if (isBackside) {
          // Dim to 30% on backside, fade to 0 as uHideBackside increases
          backsideFade = 0.3 * (1.0 - uHideBackside);
          if (backsideFade < 0.01) discard;
        }

        // Boost visibility in bright sunlight (satellite mode only)
        float sunBoost = 1.0;
        if (uSatelliteEnabled) {
          vec3 sphereNormal = normalize(vWorldPosition);
          vec3 sunDir = normalize(uSunDirection);
          float sunDot = dot(sphereNormal, sunDir);
          // Day factor: 0 on night side, 1 on day side
          float dayFactor = smoothstep(-0.2, 0.3, sunDot);
          // Boost opacity in bright areas: 1.0 in shadow, up to 2.0 in full sunlight
          // Fill needs more boost than borders since it's more transparent
          sunBoost = mix(1.0, 2.0, dayFactor);
        }

        float finalOpacity = min(uOpacity * sunBoost * backsideFade, 0.4);  // Cap at 0.4 to not be too opaque
        gl_FragColor = vec4(uColor, finalOpacity);
      }
    `,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    side: THREE.DoubleSide,
    blending: THREE.NormalBlending,
    // STENCIL BUFFER: Draw where stencil is non-zero (odd count = inside polygon)
    stencilWrite: true,
    stencilFunc: THREE.NotEqualStencilFunc,  // Only draw where stencil != 0
    stencilRef: 0,
    stencilZPass: THREE.ZeroStencilOp,       // Reset stencil after drawing to allow next empire
  })
  return mat
}

/**
 * Update camera uniforms on empire/polygon materials
 */
export function updateEmpireMaterialUniforms(
  materials: THREE.ShaderMaterial[],
  cameraPosition: THREE.Vector3,
  cameraDistance: number,
  hideBackside: number = 0
): void {
  materials.forEach(mat => {
    if (mat.uniforms.uCameraPos) mat.uniforms.uCameraPos.value.copy(cameraPosition)
    if (mat.uniforms.uCameraDist) mat.uniforms.uCameraDist.value = cameraDistance
    if (mat.uniforms.uHideBackside) mat.uniforms.uHideBackside.value = hideBackside
  })
}

/**
 * Update sun direction on empire materials
 */
export function updateEmpireSunDirection(materials: THREE.ShaderMaterial[], sunDirection: THREE.Vector3): void {
  materials.forEach(mat => {
    if (mat.uniforms.uSunDirection) mat.uniforms.uSunDirection.value.copy(sunDirection)
  })
}

/**
 * Update satellite mode on empire materials
 */
export function updateEmpireSatelliteMode(materials: THREE.ShaderMaterial[], enabled: boolean): void {
  materials.forEach(mat => {
    if (mat.uniforms.uSatelliteEnabled) mat.uniforms.uSatelliteEnabled.value = enabled
  })
}

/**
 * Update opacity on empire fill material
 */
export function updateEmpireOpacity(material: THREE.ShaderMaterial, opacity: number): void {
  if (material.uniforms.uOpacity) material.uniforms.uOpacity.value = opacity
}
