import React from 'react';
import {interpolate,spring,useCurrentFrame,useVideoConfig} from 'remotion';
import {clamp,evaporation,runoff} from './motion.mjs';
import type {SceneType} from './types';

const V='#7b5cf0',BLUE='#529edb';
const Cloud:React.FC<{scale:number}>=({scale})=><g transform={`translate(480 235) scale(${scale})`}>
  <path d="M-150,40 C-200,0 -155,-52 -108,-38 C-110,-115 -5,-130 24,-67 C95,-97 155,-38 130,10 C198,6 207,67 143,73 L-132,73 C-178,72 -194,53 -150,40Z" fill="#fff" stroke="#d3c7f7" strokeWidth="5"/>
  <path d="M-100,46 Q0,64 112,42" stroke="#ede7ff" strokeWidth="8" fill="none"/>
</g>;

export const ConceptAnimation:React.FC<{type:SceneType}>=({type})=>{
  const frame=useCurrentFrame(),{fps}=useVideoConfig();const sec=frame/fps;
  const all=type==='overview';
  const active=(p:SceneType)=>all||type===p;
  const cloudScale=active('condensation')?interpolate(clamp(sec/3),[0,1],[.22,1]):1;
  const enter=spring({frame,fps,config:{damping:24,mass:1.2}});
  return <svg data-concept={type} viewBox="0 0 900 920" style={{width:'100%',height:'100%'}} aria-label="물의 순환 모형">
    <defs>
      <linearGradient id="sky" x2="0" y2="1"><stop stopColor="#efe8ff"/><stop offset="1" stopColor="#faf8ff"/></linearGradient>
      <linearGradient id="sea" x2="0" y2="1"><stop stopColor="#80c8e4"/><stop offset="1" stopColor="#529edb"/></linearGradient>
    </defs>
    <rect width="900" height="920" rx="30" fill="url(#sky)"/>
    <g opacity={.65+.35*enter}>
      {Array.from({length:12},(_,i)=>{const a=i*Math.PI/6+sec*.025;return <line key={i} x1={145+Math.cos(a)*86} y1={145+Math.sin(a)*86} x2={145+Math.cos(a)*110} y2={145+Math.sin(a)*110} stroke="#f4c755" strokeWidth="9" strokeLinecap="round"/>;})}
      <circle cx="145" cy="145" r="64" fill="#ffd969"/><text x="145" y="264" textAnchor="middle" fontSize="30" fontWeight="800" fill="#947322">태양 에너지</text>
    </g>
    <path d="M0 660 L235 405 L350 550 L440 485 L700 780 L900 850 L900 920 L0 920Z" fill="#bdd8c6"/>
    <path d="M85 650 L235 405 L350 550 L295 545 L236 475 L175 570Z" fill="#93b9ac"/>
    <path d="M200 453 L235 405 L270 454 L244 441 L228 460Z" fill="#f7fcfa"/>
    <path d="M0 795 Q200 745 395 795 Q570 840 900 765 L900 920 L0 920Z" fill="url(#sea)"/>
    <path d="M360 575 C390 705 570 690 755 805" stroke="#fff" strokeWidth="29" fill="none" strokeLinecap="round"/>
    <path d="M360 575 C390 705 570 690 755 805" stroke="#76bddd" strokeWidth="18" fill="none" strokeLinecap="round"/>
    {[0,1,2].map(i=><path key={i} d={`M${20+i*70} ${845+i*27} Q${185+i*70} ${827+i*27+Math.sin(sec*1.2+i)*5} ${360+i*130} ${848+i*27}`} fill="none" stroke="#d9f2ff" strokeWidth="5" opacity=".6"/>)}
    <g transform={`translate(${Math.sin(sec*.4)*5} 0)`}><Cloud scale={cloudScale}/></g>
    {active('evaporation')&&Array.from({length:16},(_,i)=>{
      const p=(sec/3.1+i/16)%1;const pos=evaporation(p,(i%3)-1);
      return <circle data-particle="vapor" key={i} cx={pos.x} cy={pos.y} r={5+(i%3)*2} fill={V} opacity={Math.sin(p*Math.PI)*.65}/>;
    })}
    {active('condensation')&&Array.from({length:18},(_,i)=>{
      const t=clamp(sec/3.2),a=i*2.4,r=140*(1-t)+35;
      return <circle data-particle="condensed-water" key={i} cx={480+Math.cos(a)*r} cy={235+Math.sin(a)*r*.5} r={3+t*4} fill={BLUE} opacity={1-t*.45}/>;
    })}
    {active('precipitation')&&Array.from({length:22},(_,i)=>{
      const t=(sec/1.7+i/22)%1,x=330+(i%8)*25;
      return <path data-particle="rain" key={i} d={`M${x} ${330+t*280} l-6 17`} stroke={BLUE} strokeWidth="6" strokeLinecap="round" opacity={Math.sin(t*Math.PI)}/>;
    })}
    {active('collection')&&Array.from({length:12},(_,i)=>{
      const p=(sec/3+i/12)%1,pos=runoff(p);
      return <circle data-particle="runoff" key={i} cx={pos.x} cy={pos.y} r="7" fill="#eafaff" stroke="#368dcc" strokeWidth="2"/>;
    })}
    <g fontSize="30" fontWeight="800" fill="#544773">
      <text x="735" y="840">바다</text><text x="260" y="680">강</text>
      <text x="465" y="368" textAnchor="middle">{active('condensation')?'작은 물방울·얼음 입자 → 구름':'구름'}</text>
      {active('evaporation')&&<text x="685" y="480" textAnchor="middle" fill={V}>증발</text>}
      {active('precipitation')&&<text x="540" y="505" fill={BLUE}>강수</text>}
      {active('collection')&&<text x="570" y="640" fill="#377c98">유출·집수</text>}
    </g>
    <rect x="20" y="865" width="860" height="43" rx="12" fill="#ffffffed"/>
    <text x="38" y="894" fontSize="22" fill="#544773">수증기는 보이지 않는 기체예요. 점은 이동을 나타낸 모형이에요.</text>
  </svg>;
};
