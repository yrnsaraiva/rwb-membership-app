import {Composition} from "remotion";
import {RWBFacts} from "./RWBFacts";
import {FPS, TOTAL} from "./facts";

export const Root = () => (
  <Composition id="RWBFacts" component={RWBFacts} durationInFrames={TOTAL} fps={FPS} width={1080} height={1920} />
);
