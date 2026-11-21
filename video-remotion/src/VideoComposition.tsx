import React from 'react';
import {AbsoluteFill,Html5Audio,Img,Sequence,interpolate,spring,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import {ConceptAnimation} from './ConceptAnimation';
import {clamp,localAsset} from './motion.mjs';
import type {Scene,VideoProps} from './types';

const ink='#2d2345',violet='#7b5cf0';
const font='"Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", sans-serif';

export const BackgroundLayer:React.FC<{src:string|null}>=({src})=>{
  const frame=useCurrentFrame(),{durationInFrames}=useVideoConfig();
  return <AbsoluteFill style={{background:'#f9f7ff',overflow:'hidden'}}>{src&&localAsset(src)&&<Img src={staticFile(src)} style={{width:'100%',height:'100%',objectFit:'cover',transform:`scale(${1+.025*clamp(frame/durationInFrames)})`,opacity:.8}}/>}</AbsoluteFill>;
};
export const BrandOverlay:React.FC<{topic:string}>=({topic})=><div style={{position:'absolute',top:56,left:72,right:72,display:'flex',alignItems:'center',justifyContent:'space-between',gap:24}}>
  <div style={{padding:'6px 16px',background:'#faf8fff2',borderRadius:20,display:'flex',alignItems:'center',gap:20}}><b style={{fontSize:62,color:violet,letterSpacing:-4}}>아하!</b><span style={{fontSize:24,fontWeight:800}}>개념이 보이는 순간</span></div>
  <div style={{fontSize:27,fontWeight:800,maxWidth:390,overflow:'hidden',whiteSpace:'nowrap',textOverflow:'ellipsis',background:'#faf8fff2',padding:'12px 20px',borderRadius:20}}>{topic}</div>
</div>;

export const TransitionLayer:React.FC<{duration:number;children:React.ReactNode}>=({duration,children})=>{
  const f=useCurrentFrame(),{fps}=useVideoConfig();const edge=Math.max(1,Math.min(Math.round(fps*.25),Math.floor(duration/3)));
  const opacity=interpolate(f,[0,edge,Math.max(edge+1,duration-edge),duration],[0,1,1,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
  const move=spring({frame:f,fps,config:{damping:25}});
  return <AbsoluteFill style={{opacity,transform:`translateY(${(1-move)*24}px)`}}>{children}</AbsoluteFill>;
};

export type VisualProps = {sceneIndex:number;progress:number};
type DynamicVisual = React.ComponentType<VisualProps>;
export const SceneRenderer:React.FC<{scene:Scene;duration:number;topic:string;visual?:DynamicVisual;sceneIndex?:number}>=({scene,duration,topic,visual:Visual,sceneIndex=0})=>{
  const f=useCurrentFrame(),{fps}=useVideoConfig();
  const water=topic.includes('물')&&topic.includes('순환');
  const active=water?(scene.type==='introduction'||scene.type==='overview'?'overview':scene.type):'text_explanation';
  const pages=scene.explanation.match(/.{1,96}/gu)||[scene.explanation];
  const page=pages[Math.min(pages.length-1,Math.floor(f/duration*pages.length))];
  return <TransitionLayer duration={duration}>
    <div data-safe="title" style={{position:'absolute',top:182,left:72,width:936,height:196,padding:24,borderRadius:28,background:'#faf8fff5'}}>
      <div style={{fontSize:23,fontWeight:800,color:violet,letterSpacing:2}}>{topic} · 학습 숏츠</div>
      <h1 style={{fontSize:scene.title.length>24?43:57,lineHeight:1.25,margin:'12px 0 0',wordBreak:'keep-all',overflowWrap:'anywhere'}}>{scene.title}</h1>
    </div>
    <div data-safe="concept" style={{position:'absolute',left:56,top:418,width:968,height:1070,borderRadius:38,background:'#ffffffee',border:'2px solid #e9e1fb',boxShadow:'0 20px 60px #46376512',overflow:'hidden'}}>
      <div style={{height:895,padding:'24px 24px 0',transform:`scale(${.985+.015*clamp(f/(fps*.6))})`}}>
        {Visual ? <div style={{width:'100%',height:'100%',overflow:'hidden',position:'relative',isolation:'isolate',contain:'strict'}}>
          <Visual sceneIndex={sceneIndex} progress={clamp(f/Math.max(1,duration-1))}/>
        </div> : active==='text_explanation'?<div style={{padding:60,fontSize:44,lineHeight:1.55,whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{page}</div>:<ConceptAnimation type={active}/>}
      </div>
      <div style={{padding:'18px 34px',fontSize:29,lineHeight:1.45,color:'#675b80',wordBreak:'keep-all'}}>{scene.explanation}</div>
    </div>
  </TransitionLayer>;
};

export const NarrationText:React.FC<{text:string;age:number}>=({text,age})=>{
  const {fps}=useVideoConfig();const y=interpolate(age,[0,fps*.18],[10,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
  const terms=/(태양 에너지|수증기|작은 물방울|얼음 입자|구름|비나 눈|바다|순환)/g;
  return <div style={{transform:`translateY(${y}px)`,opacity:clamp(age/(fps*.12))}}>{text.split(terms).map((part,i)=><span key={i} style={{color:i%2?'#ffdf79':'white',fontWeight:i%2?800:600}}>{part}</span>)}</div>;
};
export const SubtitleLayer:React.FC<Pick<VideoProps,'captions'|'reviewPrompt'|'topic'>>=({captions,reviewPrompt,topic})=>{
  const f=useCurrentFrame(),{fps}=useVideoConfig(),sec=f/fps;
  const cue=captions.find(c=>sec>=c.start_seconds&&sec<c.end_seconds);
  const done=captions.length>0&&sec>=captions[captions.length-1].end_seconds;
  const text=cue?.text||(done?reviewPrompt:topic.includes('물')&&topic.includes('순환')?'물은 어떤 과정을 거쳐 순환할까요?':'핵심 개념을 차근차근 살펴볼까요?');
  return <div data-safe="subtitle" style={{position:'absolute',left:72,top:1540,width:936,height:260,display:'flex',alignItems:'center',padding:'30px 36px',borderRadius:32,background:'#2d2345',color:'white',fontSize:text.length>120?26:text.length>82?30:text.length>56?36:42,lineHeight:1.45,wordBreak:'keep-all',overflowWrap:'anywhere'}}><NarrationText text={text} age={cue?f-Math.round(cue.start_seconds*fps):fps}/></div>;
};
export const AudioTrack:React.FC<Pick<VideoProps,'audio'|'audioOffset'>>=({audio,audioOffset})=>{
  const {fps}=useVideoConfig();
  return audio&&localAsset(audio)?<Sequence from={Math.round(audioOffset*fps)}><Html5Audio src={staticFile(audio)}/></Sequence>:null;
};

export const VideoComposition:React.FC<VideoProps & {visual?:DynamicVisual}>=props=>{
  const f=useCurrentFrame(),{fps,durationInFrames}=useVideoConfig();
  return <AbsoluteFill style={{fontFamily:font,color:ink}}>
    <BackgroundLayer src={props.background}/>
    {props.scenes.map((scene,sceneIndex)=>{
      const from=Math.round(scene.start_seconds*fps),duration=Math.round(scene.end_seconds*fps)-from;
      if(duration<1)return null; // A coarse preview may not sample a short scene.
      return <Sequence key={scene.id} from={from} durationInFrames={duration}><SceneRenderer scene={scene} duration={duration} topic={props.topic} visual={props.visual} sceneIndex={sceneIndex}/></Sequence>;
    })}
    <BrandOverlay topic={props.topic}/><SubtitleLayer captions={props.captions} reviewPrompt={props.reviewPrompt} topic={props.topic}/><AudioTrack audio={props.audio} audioOffset={props.audioOffset}/>
    <div style={{position:'absolute',top:1840,left:72,fontSize:22,color:'#6f6482',background:'#faf8ffef',borderRadius:12,padding:'6px 14px'}}>{!props.visual&&props.topic.includes('순환')?'개념을 설명하기 위한 모형 · 증산·지하수 저장은 생략':'설명용 학습 모형 · 명세 검토 필요'}</div>
    <div style={{position:'absolute',bottom:0,left:0,width:`${100*f/durationInFrames}%`,height:10,background:violet}}/>
  </AbsoluteFill>;
};
