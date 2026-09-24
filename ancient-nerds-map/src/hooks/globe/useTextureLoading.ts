/**
 * useTextureLoading - the globe's basemap textures
 *
 * - Critical path: only the gray basemap at the start tier (the smallest file
 *   that renders the first frame at full detail on this canvas), decoded off
 *   the main thread and uploaded before any render samples it. Its failure is
 *   a start failure (onStartError), never "counted as loaded".
 * - Background (queue tasks, see basemapPlan): the satellite at the start tier
 *   and the gray at the maximum tier, both through the strip upload.
 * - The satellite counts as ready once its texture is on the GPU
 *   (satelliteReady); while it is switched on and a texture of it is on the GPU
 *   (satelliteOnGpu), its maximum tier follows, and switching it off aborts
 *   that upload.
 * - A WebGL context loss drops both basemaps (every bitmap is closed once it is
 *   on the GPU); the restore loads the start tier again, then what had been
 *   loaded on top of it: the gray's maximum tier, and the satellite's while it
 *   is switched on (the max-tier effect, once satelliteOnGpu is back). The
 *   satellite stays ready through the loss (Mapbox and the dot colours follow
 *   it, not this canvas); a failed reload ends it.
 * - Low FPS warning delay.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import type { GlobeRefs } from './types'
import { getBasemapTier, getStartTier, tierRank, type BasemapTier } from '../../utils/deviceTier'
import {
  BasemapState,
  disposeBasemaps,
  loadSatellite as loadSatelliteTier,
  loadStartGray,
  nextAnimationFrame,
  releaseOnContextLost,
  reloadAfterContextRestored,
  restoreGray,
  upgradeGray as upgradeGrayTier,
  UploadLock,
  type BasemapContext,
} from '../../services/basemapUpgrade'
import { trackBackgroundFailure } from '../../analytics/globeBackground'

interface UseTextureLoadingOptions {
  refs: GlobeRefs
  sceneReady: boolean
  /** The visitor switched the satellite on (the shader shows it while satelliteOnGpu). */
  satelliteRequested: boolean
  /** Contract C0: the start-tier gray failed. Called once; the load is never retried. */
  onStartError: (phase: string, err: unknown) => void
  /** The satellite could not be loaded: the toggle must stop waiting for it. */
  onSatelliteFailed: () => void
}

/** Background work this device needs; the queue adds a task only where the flag is true. */
export interface BasemapPlan {
  /** Queue task 'satellite' (desktops whose maximum tier is high); touch devices load it on the first toggle. */
  preloadSatellite: boolean
  /** Queue task 'basemap': the maximum tier is above the start tier. */
  upgradeGray: boolean
}

/** What a device with these tiers loads in the background. */
export function basemapPlanFor(tiers: { start: BasemapTier; max: BasemapTier }): BasemapPlan {
  return { preloadSatellite: tiers.max === 'high', upgradeGray: tierRank(tiers.max) > tierRank(tiers.start) }
}

interface UseTextureLoadingReturn {
  /** The start-tier gray is on the GPU and in every basemap material. */
  texturesReady: boolean
  /** Same moment as texturesReady (rotation gate and the Offline-Mode button keep their timing). */
  backgroundLoadingComplete: boolean
  lowFpsReady: boolean
  /** A satellite texture reached the GPU and no reload of it failed since; stays true through a context loss. */
  satelliteReady: boolean
  /** A satellite texture is in every basemap material now (false from a context loss until the restore commits one). */
  satelliteOnGpu: boolean
  /** null until the scene exists. */
  basemapPlan: BasemapPlan | null
  /** Queue task 'satellite': the satellite at the start tier. Rejects on failure. */
  loadSatellite: (signal: AbortSignal) => Promise<void>
  /** Queue task 'basemap': the gray at the maximum tier. Rejects on failure. */
  upgradeGray: (signal: AbortSignal) => Promise<void>
  /** The satellite is requested but not ready: load it now (joins a running load) and report a failure itself. */
  requestSatellite: () => void
}

export function useTextureLoading({
  refs,
  sceneReady,
  satelliteRequested,
  onStartError,
  onSatelliteFailed,
}: UseTextureLoadingOptions): UseTextureLoadingReturn {
  const [texturesReady, setTexturesReady] = useState(false)
  const [backgroundLoadingComplete, setBackgroundLoadingComplete] = useState(false)
  const [lowFpsReady, setLowFpsReady] = useState(false)
  const [satelliteReady, setSatelliteReady] = useState(false)
  const [satelliteOnGpu, setSatelliteOnGpu] = useState(false)
  const [basemapPlan, setBasemapPlan] = useState<BasemapPlan | null>(null)

  // Callbacks from the parent change identity every render; the effects read them here.
  const onStartErrorRef = useRef(onStartError)
  const onSatelliteFailedRef = useRef(onSatelliteFailed)
  onStartErrorRef.current = onStartError
  onSatelliteFailedRef.current = onSatelliteFailed

  /** The textures of the current scene; null before sceneReady and after unmount. */
  const ctxRef = useRef<BasemapContext | null>(null)
  /** Aborts background loads the hook started itself (requests, restore re-requests); renewed per scene. */
  const ownLoadsRef = useRef<AbortController | null>(null)

  const sceneContext = useCallback((): BasemapContext => {
    const ctx = ctxRef.current
    if (!ctx) throw new Error('basemap: the scene is not ready')
    return ctx
  }, [])

  /**
   * The satellite at the start tier; a failure ends the toggle's wait (and a
   * satellite a context restore could not bring back), the caller reports it.
   * That includes the background queue stopping the task at its deadline (an
   * abort); only an unmount, which takes the scene along, leaves nobody waiting.
   */
  const loadSatellite = useCallback(async (signal: AbortSignal): Promise<void> => {
    const ctx = sceneContext()
    try {
      await loadSatelliteTier(ctx, ctx.tiers.start, signal)
    } catch (err) {
      if (ctxRef.current === ctx) {
        setSatelliteReady(false)
        onSatelliteFailedRef.current()
      }
      throw err
    }
  }, [sceneContext])

  const upgradeGray = useCallback((signal: AbortSignal): Promise<void> => upgradeGrayTier(sceneContext(), signal), [sceneContext])

  /** Runs a load the hook owns (no queue behind it): a failure is reported here, an abort is not a failure. */
  const runOwn = useCallback((task: 'satellite' | 'basemap', load: (signal: AbortSignal) => Promise<void>): void => {
    const own = ownLoadsRef.current
    if (!own) throw new Error('basemap: the scene is not ready')
    load(own.signal).catch(err => {
      if (own.signal.aborted) return // unmounted: the loads were cancelled on purpose
      trackBackgroundFailure(task, err)
    })
  }, [])

  const requestSatellite = useCallback(() => runOwn('satellite', loadSatellite), [runOwn, loadSatellite])

  // The start-tier gray, as soon as the scene exists. Nothing else is on the critical path.
  useEffect(() => {
    if (!sceneReady) return
    const sceneData = refs.scene.current
    const basemapMesh = refs.basemapMesh.current
    const backMesh = refs.basemapBackMesh.current
    if (!sceneData || !basemapMesh || !backMesh) throw new Error('useTextureLoading: sceneReady without the basemap meshes')
    const { renderer } = sceneData
    const maxTextureSize = renderer.capabilities.maxTextureSize
    const tiers = {
      start: getStartTier(maxTextureSize, { cssHeight: window.innerHeight, dpr: window.devicePixelRatio }),
      max: getBasemapTier(maxTextureSize),
    }
    const ctx: BasemapContext = {
      renderer,
      // main + the four sections + back: every material with the basemap samplers
      materials: [basemapMesh, ...refs.basemapSectionMeshes.current, backMesh].map(m => m.material as THREE.ShaderMaterial),
      tiers,
      gray: new BasemapState(),
      satellite: new BasemapState(),
      uploads: new UploadLock(),
      nextFrame: nextAnimationFrame,
      onSatelliteTexture: onGpu => {
        setSatelliteOnGpu(onGpu)
        if (onGpu) setSatelliteReady(true)
      },
    }
    ctxRef.current = ctx
    const own = new AbortController()
    ownLoadsRef.current = own
    setBasemapPlan(basemapPlanFor(tiers))

    const start = new AbortController()
    loadStartGray(ctx, start.signal).then(
      () => {
        // Unmounted: the load was cut short and handed over (disposeBasemaps), nothing to mark
        if (start.signal.aborted) return
        refs.backgroundLoadingComplete.current = true
        setBackgroundLoadingComplete(true)
        setTexturesReady(true)
      },
      (err: unknown) => {
        if (start.signal.aborted) return // unmounted: nothing to report
        onStartErrorRef.current('basemap', err)
      },
    )

    // The basemaps cannot come back from their (closed) images: they leave the
    // materials on the loss, since the first render after the restore may run in
    // a listener before ours (sceneInit restarts the loop). The restore loads them again.
    const canvas = renderer.domElement
    const onLost = () => releaseOnContextLost(ctx)
    const onRestored = () => {
      const redo = reloadAfterContextRestored(ctx)
      if (redo.gray) runOwn('basemap', signal => restoreGray(ctx, signal))
      // The start tier only: its commit brings satelliteOnGpu back, and the
      // max-tier effect below loads the maximum tier if the satellite is on.
      if (redo.satellite) runOwn('satellite', loadSatellite)
    }
    canvas.addEventListener('webglcontextlost', onLost)
    canvas.addEventListener('webglcontextrestored', onRestored)

    return () => {
      canvas.removeEventListener('webglcontextlost', onLost)
      canvas.removeEventListener('webglcontextrestored', onRestored)
      start.abort(new Error('basemap: globe unmounted'))
      own.abort(new Error('basemap: globe unmounted'))
      disposeBasemaps(ctx)
      ctxRef.current = null
      ownLoadsRef.current = null
    }
  }, [sceneReady, refs.scene, refs.basemapMesh, refs.basemapBackMesh, refs.basemapSectionMeshes, refs.backgroundLoadingComplete, runOwn, loadSatellite])

  // While the satellite is on, its maximum tier follows; switching it off aborts
  // that upload. After a context restore it runs again once the start tier is back.
  useEffect(() => {
    const ctx = ctxRef.current
    if (!ctx || !satelliteRequested || !satelliteOnGpu) return
    const held = ctx.satellite.tier
    if (held !== null && tierRank(held) >= tierRank(ctx.tiers.max)) return
    const upgrade = new AbortController()
    loadSatelliteTier(ctx, ctx.tiers.max, upgrade.signal).catch(err => {
      if (upgrade.signal.aborted) return // switched off or unmounted
      trackBackgroundFailure('satellite', err)
    })
    return () => upgrade.abort(new Error('basemap: satellite switched off'))
  }, [satelliteRequested, satelliteOnGpu])

  // Delay low FPS warning until scene is fully loaded + 3 second buffer
  useEffect(() => {
    if (!sceneReady) return
    const timer = setTimeout(() => setLowFpsReady(true), 3000)
    return () => clearTimeout(timer)
  }, [sceneReady])

  // CRITICAL: Force basemap visible when textures become ready
  // This is a separate effect to ensure it runs when texturesReady state changes
  useEffect(() => {
    refs.texturesReady.current = texturesReady

    if (!texturesReady) return

    // Force basemap visible
    const basemapMesh = refs.basemapMesh.current
    if (basemapMesh && !basemapMesh.visible) {
      basemapMesh.visible = true
    }

    // Hide globe base visual (set opacity to 0, NOT visible=false which hides children/vector layers)
    const sceneData = refs.scene.current
    const globeBase = sceneData?.globe
    if (globeBase && basemapMesh?.visible) {
      const globeMaterial = globeBase.material as THREE.MeshBasicMaterial
      globeMaterial.opacity = 0
    }

    // Force render if we have a scene (the texture is already on the GPU: no upload here)
    if (sceneData) {
      const { renderer, scene, camera } = sceneData
      renderer.render(scene, camera)
    }
  }, [texturesReady, refs.texturesReady, refs.basemapMesh, refs.scene])

  return {
    texturesReady,
    backgroundLoadingComplete,
    lowFpsReady,
    satelliteReady,
    satelliteOnGpu,
    basemapPlan,
    loadSatellite,
    upgradeGray,
    requestSatellite,
  }
}
