import React from "react";
import { Composition } from "remotion";
import { Scene, sceneSchemaDefaults } from "./Scene";

// One composition, parameterised by props. A composition per template would put
// the template list in two places (here and templates.py) and they would drift.
//
// Width/height/fps are the pinned delivery format (§11.6, rtime.py). fps=30 with
// 48 kHz audio is §11.4's exact 1600-samples-per-frame identity; changing it
// here without changing rtime.FPS breaks sample-accurate concat.
//
// durationInFrames comes from PROPS via calculateMetadata, not from a constant.
// The resolver (§11.2 phase one) has already decided every scene's length in
// whole frames; a default here would be a second opinion about duration, and
// two sources of truth about time is exactly what R1 exists to prevent.
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="scene"
      component={Scene as never}
      durationInFrames={sceneSchemaDefaults.durationInFrames}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={sceneSchemaDefaults}
      calculateMetadata={({ props }) => ({
        durationInFrames: (props as { durationInFrames?: number })
          .durationInFrames ?? sceneSchemaDefaults.durationInFrames,
      })}
    />
  );
};
