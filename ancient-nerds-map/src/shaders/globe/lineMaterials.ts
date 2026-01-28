import * as THREE from 'three'

/**
 * Shader material for FRONT-facing lines (current detail level)
 * Uses horizon-based culling to show only lines facing the camera
 * Features: sun lighting boost for satellite mode, MAX blending for clean overlaps
 */
export function createFrontLineMaterial(color: number, opacity: number = 1): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uCameraPos: { value: new THREE.Vector3() },
      uOpacity: { value: opacity },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 }, // Camera distance for zoom-based cutoff
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

        // Calculate facing
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(worldPos.xyz);
        vFacing = dot(surfaceNormal, toCamera);

        // Mathematical horizon for unit sphere: cutoff = 1/distance
        vHorizon = 1.0 / uCameraDist;

        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform vec3 uSunDirection;
      uniform bool uSatelliteEnabled;
      varying vec3 vWorldPosition;
      varying float vFacing;
      varying float vHorizon;
      void main() {
        if (uOpacity < 0.01) discard;  // Hide when opacity is 0
        // Discard backside (handled by separate back material at 10%)
        if (vFacing < vHorizon) discard;

        // Boost visibility in bright sunlight (satellite mode only)
        float sunBoost = 1.0;
        if (uSatelliteEnabled) {
          vec3 sphereNormal = normalize(vWorldPosition);
          vec3 sunDir = normalize(uSunDirection);
          float sunDot = dot(sphereNormal, sunDir);
          // Day factor: 0 on night side, 1 on day side
          float dayFactor = smoothstep(-0.2, 0.3, sunDot);
          // Boost opacity in bright areas: 1.0 in shadow, up to 1.5 in full sunlight
          sunBoost = mix(1.0, 1.5, dayFactor);
        }

        float finalOpacity = min(uOpacity * sunBoost, 1.0);
        // Multiply color by opacity so MAX blending works correctly when opacity is 0
        gl_FragColor = vec4(uColor * finalOpacity, finalOpacity);
      }
    `,
    transparent: true,
    depthWrite: false,
    // MAX blending: overlapping lines (shared polygon edges) don't get brighter
    blending: THREE.CustomBlending,
    blendEquation: THREE.MaxEquation,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneFactor,
  })
}

/**
 * Shader material for BACK-facing lines (always low detail)
 * Shows lines on the back of the globe at 75% darker
 */
export function createBackLineMaterial(color: number, opacity: number = 1): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uCameraPos: { value: new THREE.Vector3() },
      uOpacity: { value: opacity },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 } // Camera distance for zoom-based cutoff
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

        // Calculate facing
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(worldPos.xyz);
        vFacing = dot(surfaceNormal, toCamera);

        // Same horizon calculation as front material
        vHorizon = 1.0 / uCameraDist;

        gl_Position = projectionMatrix * viewMatrix * worldPos;
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform float uHideBackside;
      varying vec3 vWorldPosition;
      varying float vFacing;
      varying float vHorizon;
      void main() {
        // Show lines below horizon (same as front material threshold)
        if (vFacing >= vHorizon) discard;

        // Smooth fade when zooming in
        float fadeOut = 1.0 - uHideBackside;
        if (fadeOut < 0.01) discard;

        // 75% darker on backside
        vec3 darkColor = uColor * 0.25;
        float alpha = uOpacity * fadeOut;

        gl_FragColor = vec4(darkColor, alpha);
      }
    `,
    transparent: true,
    depthWrite: false
  })
}

/**
 * Update camera uniforms on line materials
 */
export function updateLineMaterialUniforms(
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
 * Update sun direction on line materials
 */
export function updateLineSunDirection(materials: THREE.ShaderMaterial[], sunDirection: THREE.Vector3): void {
  materials.forEach(mat => {
    if (mat.uniforms.uSunDirection) mat.uniforms.uSunDirection.value.copy(sunDirection)
  })
}

/**
 * Update satellite mode on line materials
 */
export function updateLineSatelliteMode(materials: THREE.ShaderMaterial[], enabled: boolean): void {
  materials.forEach(mat => {
    if (mat.uniforms.uSatelliteEnabled) mat.uniforms.uSatelliteEnabled.value = enabled
  })
}

/**
 * Update opacity on a line material
 */
export function updateLineOpacity(material: THREE.ShaderMaterial, opacity: number): void {
  if (material.uniforms.uOpacity) material.uniforms.uOpacity.value = opacity
}
