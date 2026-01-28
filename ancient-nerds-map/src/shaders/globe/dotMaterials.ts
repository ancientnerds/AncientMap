import * as THREE from 'three'

/**
 * Front-side dot material - full brightness with pulsing LED glow
 * Features: sun lighting, satellite mode, pop-in animation
 * Renders after back dots for proper depth ordering
 */
export function createFrontDotMaterial(size: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uSize: { value: size },
      uCameraPos: { value: new THREE.Vector3() },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 },
      uTime: { value: 0 },
      uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
      uSatelliteEnabled: { value: false },
      uFadeIn: { value: 1.0 },  // Global fade (unused now, kept for compatibility)
      uDotsFadeProgress: { value: 0.0 }  // 0 = all hidden, 1 = all visible (dots appear randomly as this increases)
    },
    vertexShader: `
      attribute vec3 color;
      attribute float glow;
      attribute float fadeDelay;
      varying vec3 vColor;
      varying float vFacing;
      varying float vHorizon;
      varying float vGlow;
      varying vec3 vWorldPos;
      varying float vFadeIn;
      uniform float uSize;
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      uniform float uTime;
      uniform float uDotsFadeProgress;

      void main() {
        vColor = color;
        vGlow = glow;
        vWorldPos = position;
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(position);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;

        // Pop-in animation: each dot has random start time, animates over ~7% of total duration (~200ms)
        // Dots spread across first 93% to ensure all complete within 3 seconds
        float dotStart = fadeDelay * 0.93;
        float animDuration = 0.07;  // ~200ms out of 3000ms
        float dotProgress = clamp((uDotsFadeProgress - dotStart) / animDuration, 0.0, 1.0);

        // Overshoot curve: 0 -> 2x -> 1x (elastic pop)
        // Using sine-based overshoot: peaks at 2x around 40% progress, settles to 1x
        float overshoot = dotProgress < 1.0 ? sin(dotProgress * 3.14159) * 1.0 + dotProgress : 1.0;
        float sizeScale = dotProgress > 0.0 ? overshoot : 0.0;

        // Quick fade-in (full opacity by 30% of dot's animation)
        vFadeIn = clamp(dotProgress * 3.33, 0.0, 1.0);

        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        // No pulsing - constant size
        float pulse = 1.0;
        gl_PointSize = uSize * 1.2 * pulse * sizeScale;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vFacing;
      varying float vHorizon;
      varying float vGlow;
      varying vec3 vWorldPos;
      varying float vFadeIn;
      uniform float uTime;
      uniform vec3 uCameraPos;
      uniform vec3 uSunDirection;
      uniform bool uSatelliteEnabled;

      void main() {
        vec2 center = gl_PointCoord - vec2(0.5);
        float dist = length(center) * 2.0;

        // Discard pixels outside the glow radius
        if (dist > 1.0) discard;

        // Only render front-facing dots
        if (vFacing < vHorizon) discard;

        // Skip rendering if fully faded out
        if (vFadeIn < 0.01) discard;

        // Sun lighting - only apply when satellite mode is enabled
        float sunLight = 1.0;
        if (uSatelliteEnabled) {
          vec3 sphereNormal = normalize(vWorldPos);
          vec3 sunDir = normalize(uSunDirection);
          float sunDot = dot(sphereNormal, sunDir);
          // Day/night factor: 0.8 on night side, 1.0 on day side (20% difference)
          float dayFactor = smoothstep(-0.2, 0.3, sunDot);
          sunLight = mix(0.8, 1.0, dayFactor);
        }

        // Crisp dot with anti-aliased edge (no glow, no pulsing)
        if (dist < 0.9) {
          // Solid core
          gl_FragColor = vec4(vColor * sunLight, 0.85 * vFadeIn);
        } else if (dist < 1.0) {
          // Sharp anti-aliased edge
          float edge = smoothstep(1.0, 0.9, dist);
          gl_FragColor = vec4(vColor * sunLight, edge * 0.85 * vFadeIn);
        } else {
          discard;
        }
        gl_FragDepth = gl_FragCoord.z - 0.00001;
      }
    `,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    blending: THREE.NormalBlending
  })
}

/**
 * Shadow material for dots - renders BEFORE dots so shadows only appear on basemap
 * Shadow direction is aligned to the sun position for realistic lighting
 */
export function createDotShadowMaterial(size: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uSize: { value: size },
      uCameraPos: { value: new THREE.Vector3() },
      uCameraDist: { value: 2.2 },
      uSunDirection: { value: new THREE.Vector3(1.0, 0.5, 0.8).normalize() },
      uDotsFadeProgress: { value: 0.0 }  // For pop-in animation sync with dots
    },
    vertexShader: `
      attribute float fadeDelay;
      uniform float uSize;
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      uniform vec3 uSunDirection;
      uniform float uDotsFadeProgress;
      varying float vFacing;
      varying float vHorizon;
      varying vec2 vShadowOffset;
      varying float vSizeScale;

      void main() {
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(position);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;

        // Pop-in animation (same as dots)
        float dotStart = fadeDelay * 0.93;
        float animDuration = 0.07;
        float dotProgress = clamp((uDotsFadeProgress - dotStart) / animDuration, 0.0, 1.0);

        // Overshoot curve: 0 -> 2x -> 1x
        float overshoot = dotProgress < 1.0 ? sin(dotProgress * 3.14159) * 1.0 + dotProgress : 1.0;
        vSizeScale = dotProgress > 0.0 ? overshoot : 0.0;

        // Calculate shadow offset based on sun direction
        // Project sun direction onto the view plane (perpendicular to camera)
        vec3 viewRight = normalize(cross(vec3(0.0, 1.0, 0.0), toCamera));
        vec3 viewUp = normalize(cross(toCamera, viewRight));

        // Shadow is cast opposite to sun direction
        // Project -sunDirection onto the view plane
        vec3 shadowDir3D = -uSunDirection;
        float shadowX = dot(shadowDir3D, viewRight);
        float shadowY = dot(shadowDir3D, viewUp);

        // Normalize and scale the offset (keep it subtle)
        // Note: gl_PointCoord.y is inverted (0=top, 1=bottom), so negate Y
        vec2 rawOffset = vec2(shadowX, -shadowY);
        float offsetLen = length(rawOffset);
        if (offsetLen > 0.01) {
          vShadowOffset = (rawOffset / offsetLen) * 0.14;
        } else {
          // Sun is behind camera or aligned - use default offset
          vShadowOffset = vec2(0.12, 0.12);
        }

        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        // Shadow is larger than dot to create offset effect, scaled with pop-in
        gl_PointSize = uSize * 2.2 * vSizeScale;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying float vFacing;
      varying float vHorizon;
      varying vec2 vShadowOffset;
      varying float vSizeScale;

      void main() {
        // Only render front-facing
        if (vFacing < vHorizon) discard;

        // Skip if not yet visible
        if (vSizeScale < 0.01) discard;

        // Shadow offset based on sun direction (passed from vertex shader)
        vec2 shadowCenter = gl_PointCoord - vec2(0.5) - vShadowOffset;
        float shadowDist = length(shadowCenter) * 2.5;

        if (shadowDist > 1.0) discard;

        // Strong shadow with soft edge
        float innerShadow = smoothstep(1.0, 0.2, shadowDist) * 0.85;
        float outerShadow = exp(-shadowDist * 1.5) * 0.5;
        float shadowAlpha = max(innerShadow, outerShadow);

        if (shadowAlpha < 0.02) discard;

        gl_FragColor = vec4(0.0, 0.0, 0.0, shadowAlpha);
      }
    `,
    transparent: true,
    depthTest: true,
    depthWrite: false,
    blending: THREE.NormalBlending
  })
}

/**
 * Back-side dot material - blurry, dimmed with soft glow
 * Renders first (behind everything)
 */
export function createBackDotMaterial(size: number): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uSize: { value: size },
      uCameraPos: { value: new THREE.Vector3() },
      uCameraDist: { value: 2.2 },
      uHideBackside: { value: 0 },
      uTime: { value: 0 },
      uDotsFadeProgress: { value: 0.0 }  // 0 = all hidden, 1 = all visible
    },
    vertexShader: `
      attribute vec3 color;
      attribute float glow;
      attribute float fadeDelay;
      varying vec3 vColor;
      varying float vFacing;
      varying float vHorizon;
      varying float vGlow;
      varying float vFadeIn;
      uniform float uSize;
      uniform vec3 uCameraPos;
      uniform float uCameraDist;
      uniform float uTime;
      uniform float uDotsFadeProgress;

      void main() {
        vColor = color;
        vGlow = glow;
        vec3 toCamera = normalize(uCameraPos);
        vec3 surfaceNormal = normalize(position);
        vFacing = dot(surfaceNormal, toCamera);
        vHorizon = 1.0 / uCameraDist;  // Same as front dots

        // Pop-in animation (same as front dots)
        float dotStart = fadeDelay * 0.93;
        float animDuration = 0.07;
        float dotProgress = clamp((uDotsFadeProgress - dotStart) / animDuration, 0.0, 1.0);

        // Overshoot curve: 0 -> 2x -> 1x
        float overshoot = dotProgress < 1.0 ? sin(dotProgress * 3.14159) * 1.0 + dotProgress : 1.0;
        float sizeScale = dotProgress > 0.0 ? overshoot : 0.0;

        // Quick fade-in
        vFadeIn = clamp(dotProgress * 3.33, 0.0, 1.0);

        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);

        // Only render dots below horizon (same threshold as front dots)
        if (vFacing >= vHorizon) {
          gl_PointSize = 0.0;
          gl_Position = vec4(0.0);
          return;
        }

        // Same size as front dots - uniform glass effect
        float blurScale = 1.0;

        // No pulsing - constant size
        float pulse = 1.0;
        gl_PointSize = uSize * blurScale * pulse * sizeScale;
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      uniform float uHideBackside;
      uniform float uTime;
      varying vec3 vColor;
      varying float vFacing;
      varying float vHorizon;
      varying float vGlow;
      varying float vFadeIn;

      void main() {
        vec2 center = gl_PointCoord - vec2(0.5);
        float dist = length(center) * 2.0;

        // Discard pixels outside dot radius
        if (dist > 1.0) discard;

        // Only render back-facing dots (below horizon)
        if (vFacing >= vHorizon) discard;

        // Skip if not yet faded in
        if (vFadeIn < 0.01) discard;

        // Smooth fade when zooming in
        float fadeOut = 1.0 - uHideBackside;
        if (fadeOut < 0.01) discard;

        // 75% darker on backside
        vec3 darkColor = vColor * 0.25;

        // Crisp dot with anti-aliased edge (matching front dots)
        float alpha = 0.0;
        if (dist < 0.9) {
          alpha = 1.0;
        } else if (dist < 1.0) {
          alpha = smoothstep(1.0, 0.9, dist);
        }

        alpha *= fadeOut * vFadeIn;

        // Apply 30% transparency
        gl_FragColor = vec4(darkColor, alpha * 0.7);
      }
    `,
    transparent: true,
    depthTest: false,  // Ignore depth - shader handles front/back culling
    depthWrite: false
  })
}

/**
 * Update uniforms on dot materials
 */
export function updateDotMaterialUniforms(
  material: THREE.ShaderMaterial,
  cameraPosition: THREE.Vector3,
  cameraDistance: number,
  time: number,
  hideBackside: number = 0
): void {
  if (material.uniforms.uCameraPos) material.uniforms.uCameraPos.value.copy(cameraPosition)
  if (material.uniforms.uCameraDist) material.uniforms.uCameraDist.value = cameraDistance
  if (material.uniforms.uTime) material.uniforms.uTime.value = time
  if (material.uniforms.uHideBackside) material.uniforms.uHideBackside.value = hideBackside
}

/**
 * Update dot size
 */
export function updateDotSize(material: THREE.ShaderMaterial, size: number): void {
  if (material.uniforms.uSize) material.uniforms.uSize.value = size
}

/**
 * Update sun direction uniform
 */
export function updateDotSunDirection(material: THREE.ShaderMaterial, sunDirection: THREE.Vector3): void {
  if (material.uniforms.uSunDirection) material.uniforms.uSunDirection.value.copy(sunDirection)
}

/**
 * Update satellite mode
 */
export function updateDotSatelliteMode(material: THREE.ShaderMaterial, enabled: boolean): void {
  if (material.uniforms.uSatelliteEnabled) material.uniforms.uSatelliteEnabled.value = enabled
}

/**
 * Update dots fade progress for pop-in animation
 */
export function updateDotsFadeProgress(material: THREE.ShaderMaterial, progress: number): void {
  if (material.uniforms.uDotsFadeProgress) material.uniforms.uDotsFadeProgress.value = progress
}
