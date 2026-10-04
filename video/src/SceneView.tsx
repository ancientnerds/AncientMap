/**
 * One scene inside its <Sequence>: the block with scene-relative cues and its
 * stage (shorter while hook captions run), plus the scene's in-frame credit
 * line when timeline.credits names the scene and credits are drawn.
 */
import React from 'react'
import { AbsoluteFill } from 'remotion'

import { blockDef } from './blocks'
import { CreditLine } from './blocks/CreditLine'
import { mergeCredits } from './captions'
import { stageFor } from './layout/zones'
import type { Scene } from './timeline'

export const SceneView: React.FC<{ scene: Scene; credits: readonly string[]; captioned: boolean }> = ({ scene, credits, captioned }) => {
  const Block = blockDef(scene.block).component
  const cues = scene.cues.map((c) => ({ ...c, frame: c.frame - scene.from }))
  return (
    <AbsoluteFill>
      <Block props={scene.props} cues={cues} durationInFrames={scene.durationInFrames} sceneId={scene.id} sceneFrom={scene.from} stage={stageFor(captioned)} />
      {credits.length > 0 ? <CreditLine id={`${scene.id}:credit`} text={mergeCredits(credits)} /> : null}
    </AbsoluteFill>
  )
}
