import React from 'react';
import {Composition,getInputProps} from 'remotion';
import {VideoComposition} from './VideoComposition';
import type {VideoProps} from './types';

const defaults:VideoProps={topic:'물의 순환',fps:30,duration:30,audio:null,background:null,audioOffset:0,
  reviewPrompt:'증발·응결·강수·집수를 순서대로 설명해 보세요.',captions:[],
  scenes:[{id:'demo',type:'overview',start_seconds:0,end_seconds:30,title:'물은 돌고 돌아요',explanation:'태양 에너지와 물의 이동을 연결해 보세요.'}]};
export const Root:React.FC=()=>{
  const input=getInputProps() as Partial<VideoProps>;
  return <Composition id="AhaLearningShort" component={VideoComposition} width={1080} height={1920} fps={30} durationInFrames={900}
    defaultProps={{...defaults,...input}} calculateMetadata={({props})=>({fps:props.fps,durationInFrames:Math.round(props.duration*props.fps)})}/>;
};
