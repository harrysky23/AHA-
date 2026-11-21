import React from 'react';
import {Composition, getInputProps, registerRoot} from 'remotion';
import {VideoComposition} from './VideoComposition';
import type {VideoProps} from './types';
import Visual from './GeneratedVisual';

const GeneratedVideo = (props: VideoProps) => <VideoComposition {...props} visual={Visual}/>;
const Root = () => {
  const props = getInputProps() as unknown as VideoProps;
  return <Composition id="AhaLearningShort" component={GeneratedVideo}
    width={1080} height={1920} fps={props.fps} durationInFrames={props.fps * props.duration} defaultProps={props}/>;
};
registerRoot(Root);
